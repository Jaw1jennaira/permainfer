"""Model backends.

Two backends, one interface:

* :class:`LlamaCppBackend` — the real one. Loads a GGUF open-weight
  model with llama.cpp and runs inference on CPU (or GPU when
  available). This is what runs in production and on Nosana.
* :class:`EchoBackend` — a deterministic, clearly-labelled stand-in used
  ONLY by the automated tests and by ``--demo`` smoke runs when no model
  file is present. It never pretends to be a model: its ``model`` id is
  ``echo/0.1`` and every receipt it produces says so.

A backend is deliberately boring: ``generate(prompt, params)`` returns
``(text, usage_dict)``. Everything verifiable — hashing, receipts,
Arweave payloads — lives outside the backend so it works identically
no matter where the compute runs.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
HF_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-0.5b-instruct-q4_k_m.gguf"
)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


@dataclass
class GenerationParams:
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 0.9
    stop: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stop": self.stop or [],
        }


class Backend(Protocol):
    model_id: str
    model_file: str
    model_sha256: str

    def generate(self, prompt: str, params: GenerationParams) -> tuple[str, dict]:
        ...


class EchoBackend:
    """Deterministic stand-in for tests. NOT a language model.

    Returns the prompt back, wrapped, so tests can exercise the whole
    receipt/ledger/Arweave pipeline without a GPU or a model download.
    """

    model_id = "echo/0.1"
    model_file = "echo"
    model_sha256 = hashlib.sha256(b"echo-backend-no-weights").hexdigest()

    def generate(self, prompt: str, params: GenerationParams) -> tuple[str, dict]:
        text = f"[echo] {prompt.strip()}"
        usage = {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(text.split()),
            "total_tokens": len(prompt.split()) + len(text.split()),
            "wall_seconds": 0.0,
        }
        return text, usage


class LlamaCppBackend:
    """Real open-weight inference via llama.cpp (GGUF, CPU or GPU)."""

    def __init__(
        self,
        model_path: str | Path,
        model_id: str = DEFAULT_MODEL_ID,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        verbose: bool = False,
    ):
        from llama_cpp import Llama  # imported lazily: tests don't need it

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"model file not found: {model_path}. "
                f"Download it with: python scripts/download_model.py "
                f"(free, from Hugging Face: {HF_MODEL_URL})"
            )
        self.model_id = model_id
        self.model_file = model_path.name
        self.model_sha256 = sha256_file(model_path)
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=verbose,
        )

    def _chat_prompt(self, prompt: str) -> str:
        # ChatML template used by Qwen2.5-Instruct models.
        return (
            "<|im_start|>system\n"
            "You are a helpful assistant.<|im_end|>\n"
            "<|im_start|>user\n"
            f"{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

    def generate(self, prompt: str, params: GenerationParams) -> tuple[str, dict]:
        started = time.monotonic()
        out = self._llm(
            self._chat_prompt(prompt),
            max_tokens=params.max_tokens,
            temperature=params.temperature,
            top_p=params.top_p,
            stop=params.stop or ["<|im_end|>"],
            echo=False,
        )
        choice = out["choices"][0]
        text = choice["text"].strip()
        usage = dict(out.get("usage", {}))
        usage["wall_seconds"] = round(time.monotonic() - started, 3)
        return text, usage
