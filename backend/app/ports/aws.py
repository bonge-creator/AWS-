"""AWS adapters — real boto3 calls, no fakes.

boto3 is synchronous, so every call runs via asyncio.to_thread to keep the
FastAPI event loop free.
"""

import asyncio
import json
from typing import AsyncIterator, Optional

from botocore.exceptions import ClientError

from app.ports.aws_client import aws_client
from app.ports.embedder import EmbedderPort
from app.ports.extractor import ExtractionResult, ExtractorPort
from app.ports.llm import LlmPort, LlmResponse
from app.ports.storage import StoragePort

# ───────────────────────────── Storage ─────────────────────────────


class S3StorageAdapter(StoragePort):
    """S3 with SSE-KMS. Used when S3_BUCKET_NAME is configured."""

    def __init__(self, bucket: str, kms_key_id: Optional[str] = None):
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self.client = aws_client("s3")

    async def put_object(self, key, body, content_type, metadata=None) -> str:
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": body, "ContentType": content_type}
        if self.kms_key_id:
            kwargs.update(ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key_id)
        else:
            kwargs["ServerSideEncryption"] = "AES256"
        if metadata:
            kwargs["Metadata"] = {k: str(v) for k, v in metadata.items()}
        await asyncio.to_thread(self.client.put_object, **kwargs)
        return key

    async def get_object(self, key) -> bytes:
        def _get() -> bytes:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

        return await asyncio.to_thread(_get)

    async def generate_presigned_url(self, key, expires_in=60) -> str:
        # Pure local signing — no network call.
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )

    async def object_exists(self, key) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


# ───────────────────────────── Extractor ─────────────────────────────


class TextractExtractorAdapter(ExtractorPort):
    """Textract synchronous OCR (images / single-page documents only).

    NOT exercised in the hackathon sandbox: the account has an explicit IAM deny
    on textract:*, so the app defaults to the local PDF extractor there.
    Multi-page PDFs would need the async StartDocumentTextDetection + S3 flow,
    which is intentionally not implemented here.
    """

    def __init__(self):
        self.client = aws_client("textract")

    async def extract(self, document_bytes, filename, content_type) -> ExtractionResult:
        response = await asyncio.to_thread(
            self.client.detect_document_text, Document={"Bytes": document_bytes}
        )
        lines = [b["Text"] for b in response.get("Blocks", []) if b.get("BlockType") == "LINE"]
        text = "\n".join(lines)
        return ExtractionResult(text=text, page_count=1, pages=[{"page": 1, "text": text}])


# ───────────────────────────── Embedder ─────────────────────────────


class BedrockTitanEmbedderAdapter(EmbedderPort):
    """Titan Text Embeddings V2, 1024-dim, normalised (so cosine == dot product)."""

    def __init__(self, model_id: str, concurrency: int = 1):
        self._model_id = model_id
        self.client = aws_client("bedrock-runtime")
        self._sem = asyncio.Semaphore(concurrency)

    def _embed_one(self, text: str) -> list[float]:
        response = self.client.invoke_model(
            modelId=self._model_id,
            body=json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())["embedding"]

    async def _guarded(self, text: str) -> list[float]:
        async with self._sem:
            return await asyncio.to_thread(self._embed_one, text)

    async def embed(self, texts):
        return list(await asyncio.gather(*(self._guarded(t) for t in texts)))

    @property
    def model_id(self) -> str:
        return "titan-v2"


# ───────────────────────────── LLM ─────────────────────────────

JSON_INSTRUCTION = (
    "Respond with a JSON object only, no markdown fences: "
    '{"answer": string, "found": boolean, "citations": [int]}. '
    "If found is false, set answer to an empty string and citations to []. "
    "Cite each factual claim with [n] referencing the numbered context passage. "
    "Do not invent information not present in the context."
)

STREAM_INSTRUCTION = (
    "Answer in plain prose using only the numbered context passages. "
    "Cite each factual claim with the [n] marker of the passage it comes from. "
    "If the context does not answer the question, reply with exactly NO_ANSWER "
    "and nothing else. Never invent information that is not in the context."
)

_INFERENCE = {"maxTokens": 1200, "temperature": 0.1, "topP": 0.9}


class BedrockConverseLlmAdapter(LlmPort):
    """Bedrock Converse with retry and a model fallback chain.

    Bedrock's on-demand throughput throttles for two distinct reasons and
    they need different handling:

    - a burst limit ("too many requests") clears in seconds, so the call is
      retried with exponential backoff;
    - a daily token allowance ("too many tokens per day") does not clear
      within the request, so retrying the same model is pointless. The
      adapter then tries the other models the account can reach before the
      caller falls back to extractive answering.

    Whichever model answered is reported in `LlmResponse.model`, so a
    degraded answer is never passed off as a full-strength one.
    """

    def __init__(self, model_id: str, fallback_models: Optional[list] = None):
        self._model_id = model_id
        self._models = [model_id] + [m for m in (fallback_models or []) if m != model_id]
        # One botocore attempt only: this adapter retries itself, because it
        # can tell a throttle that clears in seconds from a daily allowance
        # that will not. Leaving botocore's adaptive backoff in place would
        # spend a minute retrying an allowance that cannot clear.
        self.client = aws_client("bedrock-runtime", max_attempts=1)

    def _messages(self, context, question, history):
        messages = []
        for h in (history or [])[-6:]:
            if h.get("content"):
                messages.append({"role": h["role"], "content": [{"text": h["content"]}]})
        messages.append(
            {"role": "user", "content": [{"text": f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"}]}
        )
        return messages

    def _system(self, system_prompt):
        return [{"text": system_prompt}, {"text": JSON_INSTRUCTION}]

    async def _call_with_retry(self, model_id, **kwargs):
        """Call Bedrock, retrying only throttles that can clear in seconds.

        When credit is exhausted account-wide (daily allowance), every retry
        will fail anyway — so we cap at 2 attempts to fall back to the
        extractive adapter quickly rather than burning 7 seconds on retries
        that will never succeed.
        """
        delay = 1.0
        last_error = None
        for attempt in range(2):
            try:
                return await asyncio.to_thread(
                    self.client.converse, modelId=model_id, **kwargs
                )
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                message = str(e.response.get("Error", {}).get("Message", ""))
                last_error = e
                if code != "ThrottlingException" or "per day" in message:
                    raise
                if attempt == 1:
                    raise
                await asyncio.sleep(delay)
        raise last_error  # pragma: no cover - the loop always returns or raises

    async def generate(self, system_prompt, context, question, history=None) -> LlmResponse:
        kwargs = {
            "messages": self._messages(context, question, history),
            "system": self._system(system_prompt),
            "inferenceConfig": _INFERENCE,
        }
        for model_id in self._models:
            try:
                response = await self._call_with_retry(model_id, **kwargs)
            except ClientError:
                if model_id == self._models[-1]:
                    raise
                continue
            text = "".join(
                b["text"] for b in response["output"]["message"]["content"] if "text" in b
            )
            data = _parse_json(text)
            return LlmResponse(
                text=data.get("answer") or "",
                citations=[int(c) for c in (data.get("citations") or []) if str(c).isdigit()],
                found=bool(data.get("found", True)),
                usage=response.get("usage"),
                model=model_id,
            )
        raise RuntimeError("no Bedrock model answered")  # pragma: no cover

    async def summarise(self, system_prompt, context, instruction=None) -> LlmResponse:
        """Summarise using Bedrock Converse with a summarisation instruction.

        We pass the instruction as the question and ask the model to output
        a JSON-structured summary (answer/found/citations) just like generate
        does, but the prompt language steers the model toward summarisation.
        """
        response = await self.generate(system_prompt, context, instruction or "Summarise this section in three sentences or fewer.")
        # The Bedrock model already produced structured output; return it as-is.
        return response

    async def generate_stream(
        self, system_prompt, context, question, history=None
    ) -> AsyncIterator[str]:
        kwargs = {
            "messages": self._messages(context, question, history),
            "system": [{"text": system_prompt}, {"text": STREAM_INSTRUCTION}],
            "inferenceConfig": _INFERENCE,
        }
        last_error = None
        for model_id in self._models:
            try:
                response = await asyncio.to_thread(
                    self.client.converse_stream, modelId=model_id, **kwargs
                )
            except ClientError as e:
                last_error = e
                continue
            events = iter(response["stream"])
            done = object()
            while True:
                event = await asyncio.to_thread(next, events, done)
                if event is done:
                    return
                token = event.get("contentBlockDelta", {}).get("delta", {}).get("text", "")
                if token:
                    yield token
            return
        raise last_error  # pragma: no cover


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    # Unparseable model output: treat as NOT found rather than trusting free text.
    return {"answer": "", "found": False, "citations": []}
