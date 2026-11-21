"""Resilient LLM: try Bedrock, degrade to the extractive adapter on throttling/access errors.

The fallback is never silent — LlmResponse.model records which engine answered,
and the UI shows it, so a degraded answer is not passed off as a model answer.
"""

import logging

from botocore.exceptions import BotoCoreError, ClientError

from app.ports.llm import LlmPort, LlmResponse

log = logging.getLogger(__name__)

_DEGRADE_CODES = {
    "ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException",
    "AccessDeniedException", "ResourceNotFoundException", "ModelNotReadyException",
    "TooManyRequestsException", "ValidationException",
}


class FallbackLlmAdapter(LlmPort):
    def __init__(self, primary: LlmPort, fallback: LlmPort):
        self.primary = primary
        self.fallback = fallback

    async def generate(self, system_prompt, context, question, history=None) -> LlmResponse:
        try:
            return await self.primary.generate(system_prompt, context, question, history)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in _DEGRADE_CODES:
                raise
            log.warning("Bedrock %s — falling back to extractive answer", code)
        except BotoCoreError as e:
            log.warning("Bedrock transport error (%s) — falling back", type(e).__name__)
        resp = await self.fallback.generate(system_prompt, context, question, history)
        resp.model = "extractive-fallback"
        return resp

    async def summarise(self, system_prompt, context, instruction=None) -> LlmResponse:
        try:
            return await self.primary.summarise(system_prompt, context, instruction)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in _DEGRADE_CODES:
                raise
            log.warning("Bedrock %s — falling back to extractive summary", code)
        except BotoCoreError as e:
            log.warning("Bedrock transport error (%s) — falling back", type(e).__name__)
        resp = await self.fallback.summarise(system_prompt, context, instruction)
        resp.model = "extractive-fallback"
        return resp
