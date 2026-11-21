"""Generation backends behind one small interface.

- ``VLLMBackend``: open-weight model on a GPU (Colab), JSON-schema constrained decoding, token logprobs.
  This is the primary system: the data never leaves the machine that runs it.
- ``AnthropicBackend``: Claude API comparison arm (structured outputs, no logprobs).
- ``FakeBackend``: deterministic, for tests and CI.

Heavy dependencies (vllm, anthropic) are imported lazily so the package installs without them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Request:
    key: str  # case id, used for per-request seeds
    system: str
    user: str
    schema: dict


@dataclass
class Completion:
    text: str
    tokens: list[tuple[str, float]] | None = None  # (decoded token, logprob of the sampled token)
    finish_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Backend(Protocol):
    name: str
    model_id: str  # pinned id incl. revision

    def generate(self, requests: list[Request], *, greedy: bool, n: int, seed: int) -> list[list[Completion]]:
        """One list of ``n`` completions per request (greedy implies n == 1)."""
        ...

    def describe(self) -> dict[str, Any]:
        """Everything needed to reproduce the run (versions, decoding parameters)."""
        ...


def request_seed(seed: int, key: str) -> int:
    """Stable per-request seed (independent of batch order)."""
    import hashlib

    return (seed * 1_000_003 + int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)) % (2**31 - 1)


# --------------------------------------------------------------------------------------------- fake
class FakeBackend:
    name = "fake"

    def __init__(self, respond: Callable[[Request, int], str], model_id: str = "fake@0"):
        self._respond = respond
        self.model_id = model_id

    def generate(self, requests: list[Request], *, greedy: bool, n: int, seed: int) -> list[list[Completion]]:
        out = []
        for r in requests:
            n_eff = 1 if greedy else n
            comps = []
            for i in range(n_eff):
                text = self._respond(r, -1 if greedy else i)
                # one pseudo-token per character, logprob -0.01: enough to exercise feature code
                comps.append(Completion(text, [(ch, -0.01) for ch in text], "stop"))
            out.append(comps)
        return out

    def describe(self) -> dict[str, Any]:
        return {"backend": self.name, "model_id": self.model_id}


# --------------------------------------------------------------------------------------------- vLLM
def token_texts(tokenizer: Any, ids: list[int], logprobs: list[float]) -> list[tuple[str, float]]:
    """Text of each generated token, decoded one by one with the model's tokenizer.

    vLLM 0.34 returns BPE pieces ("Ġ", "Ċ") in ``Logprob.decoded_token``, which do not concatenate to the output
    text (DECISIONS D21). Special tokens (end of turn) decode to "".
    """
    return [(tokenizer.decode([i], skip_special_tokens=True), lp) for i, lp in zip(ids, logprobs, strict=True)]



QWEN3_NONTHINKING_SAMPLING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}  # Qwen3 model card, non-thinking mode


class VLLMBackend:
    name = "vllm"

    def __init__(self, model: str, revision: str, *, dtype: str = "half", max_model_len: int = 8192,
                 gpu_memory_utilization: float = 0.90, max_tokens: int = 2048,
                 sampling: dict[str, float] | None = None, chat_template_kwargs: dict | None = None):
        from vllm import LLM

        self.model, self.revision = model, revision
        self.model_id = f"{model}@{revision}"
        self.max_tokens = max_tokens
        self.sampling = dict(sampling or QWEN3_NONTHINKING_SAMPLING)
        self.chat_template_kwargs = chat_template_kwargs if chat_template_kwargs is not None else {"enable_thinking": False}
        self.engine_args = {"dtype": dtype, "max_model_len": max_model_len, "gpu_memory_utilization": gpu_memory_utilization}
        self._llm = LLM(model=model, revision=revision, seed=0, **self.engine_args)
        self._tokenizer = self._llm.get_tokenizer()

    def _params(self, schema: dict, *, greedy: bool, n: int, seed: int):
        from vllm import SamplingParams

        # logprobs=1: top-1 plus the sampled token, which is always included
        kw: dict[str, Any] = {"max_tokens": self.max_tokens, "logprobs": 1, "seed": seed}
        kw.update({"temperature": 0.0, "n": 1} if greedy else {**self.sampling, "n": n})
        try:  # vLLM >= 0.11
            from vllm.sampling_params import StructuredOutputsParams

            kw["structured_outputs"] = StructuredOutputsParams(json=schema)
        except ImportError:  # older vLLM
            from vllm.sampling_params import GuidedDecodingParams

            kw["guided_decoding"] = GuidedDecodingParams(json=schema)
        return SamplingParams(**kw)

    def generate(self, requests: list[Request], *, greedy: bool, n: int, seed: int) -> list[list[Completion]]:
        messages = [[{"role": "system", "content": r.system}, {"role": "user", "content": r.user}] for r in requests]
        params = [self._params(r.schema, greedy=greedy, n=n, seed=request_seed(seed, r.key)) for r in requests]
        results = self._llm.chat(messages, params, use_tqdm=True, chat_template_kwargs=self.chat_template_kwargs)
        out = []
        for res in results:
            comps = []
            for o in res.outputs:
                ids = list(o.token_ids)
                toks = None
                if o.logprobs is not None:
                    lps = [float(lp[tid].logprob) for tid, lp in zip(ids, o.logprobs, strict=True)]
                    toks = token_texts(self._tokenizer, ids, lps)
                comps.append(Completion(o.text, toks, o.finish_reason, {"n_tokens": len(ids), "token_ids": ids}))
            out.append(comps)
        return out

    def describe(self) -> dict[str, Any]:
        import torch
        import vllm

        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        return {"backend": self.name, "model_id": self.model_id, "vllm": vllm.__version__, "torch": torch.__version__,
                "gpu": gpu, "engine_args": self.engine_args, "sampling": self.sampling, "max_tokens": self.max_tokens,
                "chat_template_kwargs": self.chat_template_kwargs}


# --------------------------------------------------------------------------------------------- Claude API
class AnthropicBackend:
    """Claude API comparison arm.

    - Structured outputs (``output_config.format``) give schema-valid JSON; no token logprobs are available,
      so confidence features come from self-consistency only.
    - Current Opus models do not accept temperature; repeated calls give the samples.
    - Server-side refusal fallback is enabled, and the model that actually served each call is recorded.
      Calls served by a different model are flagged (``meta.fallback``) and are not counted as the pinned arm.
    """

    name = "anthropic"
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: str = "claude-opus-5-5", *, effort: str = "medium", max_tokens: int = 16000,
                 workers: int = 4, fallbacks: bool = True):
        import anthropic

        self._client = anthropic.Anthropic()  # credentials from the environment (.env, never in code)
        self.model = self.model_id = model
        self.effort, self.max_tokens, self.workers, self.fallbacks = effort, max_tokens, workers, fallbacks

    def _one(self, r: Request) -> Completion:
        kw: dict[str, Any] = dict(
            model=self.model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": r.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": r.user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": r.schema}},
        )
        if self.fallbacks:
            resp = self._client.beta.messages.create(betas=[self.FALLBACK_BETA], fallbacks="default", **kw)
        else:
            resp = self._client.messages.create(**kw)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        iterations = getattr(resp.usage, "iterations", None) or []
        fallback = any(getattr(it, "type", None) == "fallback_message" for it in iterations)
        meta = {"served_model": resp.model, "fallback": fallback, "request_id": getattr(resp, "_request_id", None),
                "usage": resp.usage.to_dict() if hasattr(resp.usage, "to_dict") else None}
        if resp.stop_reason == "refusal":
            text = ""
        return Completion(text, None, resp.stop_reason, meta)

    def generate(self, requests: list[Request], *, greedy: bool, n: int, seed: int) -> list[list[Completion]]:
        n_eff = 1 if greedy else n
        jobs = [r for r in requests for _ in range(n_eff)]
        with ThreadPoolExecutor(self.workers) as ex:
            flat = list(ex.map(self._one, jobs))
        return [flat[i * n_eff:(i + 1) * n_eff] for i in range(len(requests))]

    def describe(self) -> dict[str, Any]:
        import anthropic

        return {"backend": self.name, "model_id": self.model_id, "anthropic_sdk": anthropic.__version__,
                "effort": self.effort, "max_tokens": self.max_tokens, "fallbacks": "default" if self.fallbacks else None,
                "note": "no temperature parameter on this model; samples are independent calls"}


def parse_json(text: str) -> dict | None:
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None
