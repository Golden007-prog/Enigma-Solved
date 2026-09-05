"""All LLM calls go through here: LM Studio's OpenAI-compatible endpoint, JSON-schema output.

Thinking is disabled per request (``reasoning_effort: "none"`` is what LM Studio maps to the
Qwen3.5 chat-template variable; ``chat_template_kwargs`` is the llama.cpp/vLLM spelling and is
harmless if ignored). Sampling comes from ``brain.prompts.SAMPLING`` per stage. Every call is
grammar-constrained by ``schemas.llm_response_format`` so the JSON always parses; a truncated
answer (``finish_reason == "length"``) is retried once with a larger token cap.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from brain import prompts, schemas

log = logging.getLogger("brain.llm")

DEFAULT_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
DEFAULT_MODEL = os.environ.get("LMSTUDIO_MODEL", "interviewer")

NO_THINK_EXTRA = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"enable_thinking": False},
}


@dataclass
class LLMStats:
    stage: str
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_s: float
    finish_reason: str | None
    retried: bool = False

    @property
    def tok_s(self) -> float | None:
        if self.completion_tokens and self.elapsed_s > 0:
            return self.completion_tokens / self.elapsed_s
        return None


class LLMError(RuntimeError):
    pass


class LLM:
    """Sync + async wrappers around one LM Studio model identifier."""

    def __init__(self, base_url: str = DEFAULT_URL, model: str = DEFAULT_MODEL, timeout_s: float = 180.0):
        from openai import AsyncOpenAI, OpenAI

        self.base_url = base_url
        self.model = model
        self._sync = OpenAI(base_url=base_url, api_key="lm-studio", timeout=timeout_s, max_retries=0)
        self._async = AsyncOpenAI(base_url=base_url, api_key="lm-studio", timeout=timeout_s, max_retries=0)

    # ------------------------------------------------------------------ health
    def health(self) -> tuple[bool, str]:
        try:
            ids = [m.id for m in self._sync.models.list().data]
        except Exception as exc:  # noqa: BLE001
            return False, f"LM Studio unreachable at {self.base_url}: {exc!r}"
        if self.model not in ids:
            return False, f"model '{self.model}' not loaded (have {ids})"
        return True, f"model '{self.model}' loaded"

    # ------------------------------------------------------------------ request building
    def _build(self, stage: str, values: dict[str, Any], model_cls: type[BaseModel], *, max_tokens: int | None) -> dict[str, Any]:
        system, user, sampling = prompts.render(stage, **values)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": sampling["temperature"],
            "top_p": sampling["top_p"],
            "max_tokens": max_tokens or sampling["max_tokens"],
            "presence_penalty": sampling.get("presence_penalty", 0.0),
            "response_format": schemas.llm_response_format(model_cls),
            "extra_body": {**NO_THINK_EXTRA, "top_k": sampling.get("top_k", 20)},
        }
        return body

    @staticmethod
    def _finish(resp: Any, stage: str, t0: float, retried: bool) -> tuple[str, LLMStats]:
        choice = resp.choices[0]
        text = choice.message.content or ""
        rc = getattr(choice.message, "reasoning_content", None)
        if rc:
            log.warning("%s: reasoning_content present (%d chars) — thinking is not fully off", stage, len(rc))
        usage = getattr(resp, "usage", None)
        stats = LLMStats(
            stage=stage,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            elapsed_s=time.perf_counter() - t0,
            finish_reason=getattr(choice, "finish_reason", None),
            retried=retried,
        )
        return text, stats

    @staticmethod
    def _parse(text: str, model_cls: type[BaseModel], stage: str) -> dict[str, Any]:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"{stage}: model returned non-JSON ({exc}): {text[:200]!r}") from exc
        # pydantic validation happens here so a schema drift fails loudly, not deep in the brain
        return model_cls.model_validate(obj).model_dump(mode="json")

    # ------------------------------------------------------------------ sync
    def json(self, stage: str, values: dict[str, Any], model_cls: type[BaseModel], *, max_tokens: int | None = None) -> tuple[dict[str, Any], LLMStats]:
        body = self._build(stage, values, model_cls, max_tokens=max_tokens)
        t0 = time.perf_counter()
        resp = self._sync.chat.completions.create(**body)
        text, stats = self._finish(resp, stage, t0, retried=False)
        if stats.finish_reason == "length":
            log.warning("%s: truncated at %s tokens, retrying with a larger cap", stage, body["max_tokens"])
            body["max_tokens"] = int(body["max_tokens"] * 1.6)
            t0 = time.perf_counter()
            resp = self._sync.chat.completions.create(**body)
            text, stats = self._finish(resp, stage, t0, retried=True)
        return self._parse(text, model_cls, stage), stats

    # ------------------------------------------------------------------ async
    async def ajson(self, stage: str, values: dict[str, Any], model_cls: type[BaseModel], *, max_tokens: int | None = None) -> tuple[dict[str, Any], LLMStats]:
        body = self._build(stage, values, model_cls, max_tokens=max_tokens)
        t0 = time.perf_counter()
        resp = await self._async.chat.completions.create(**body)
        text, stats = self._finish(resp, stage, t0, retried=False)
        if stats.finish_reason == "length":
            body["max_tokens"] = int(body["max_tokens"] * 1.6)
            t0 = time.perf_counter()
            resp = await self._async.chat.completions.create(**body)
            text, stats = self._finish(resp, stage, t0, retried=True)
        return self._parse(text, model_cls, stage), stats

    def quick(self, prompt: str, max_tokens: int = 40) -> tuple[str, LLMStats]:
        """A tiny unconstrained call for the self-test (tok/s measurement)."""
        t0 = time.perf_counter()
        resp = self._sync.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens,
            temperature=0.2, extra_body=dict(NO_THINK_EXTRA),
        )
        text, stats = self._finish(resp, "quick", t0, retried=False)
        return text, stats
