"""LLM protocol — Bedrock Converse or extractive fallback.

Two modes, because they serve different needs:

- `generate` returns a structured answer (JSON: answer / found / citations).
  Used for the non-streaming endpoints and for the deterministic answer.
- `generate_stream` yields plain-text tokens carrying inline `[n]` citation
  markers, so the answer can be streamed to the browser as it is produced.
  `NO_ANSWER` is the sentinel for "the context does not answer this".
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

NO_ANSWER = "NO_ANSWER"


@dataclass
class LlmResponse:
    text: str
    citations: List[int]  # indices into the context passages
    found: bool
    usage: Optional[dict] = None
    model: str = ""  # which engine produced this (recorded on the message for honesty)


class LlmPort(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        context: str,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> LlmResponse:
        """Generate a cited answer from retrieved context."""

    async def generate_stream(
        self,
        system_prompt: str,
        context: str,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> AsyncIterator[str]:
        """Stream text tokens. Default: yield the full answer text as one chunk."""
        response = await self.generate(system_prompt, context, question, history)
        yield response.text

    async def summarise(
        self, system_prompt: str, context: str, instruction: str = "Summarise this section in three sentences or fewer."
    ) -> LlmResponse:
        """Summarise a passage of text (not a Q&A exchange).

        Default implementation delegates to `generate` — works for LLM-backed
        adapters.  Extractive adapters override this to bypass the question-
        overlap scoring that is appropriate for Q&A but wrong for summarisation.
        """
        return await self.generate(system_prompt, context, instruction)
