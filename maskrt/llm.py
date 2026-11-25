"""The round trip: masked text to a small open instruction model on CPU, and its answers back.

The model runs in llama.cpp's own server (llama-server), started and stopped from here.
Python talks to it over HTTP on localhost; no Python binding is needed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from .ner import MODELS_DIR

GGUF_FILE = "qwen2.5-1.5b-instruct-q4_K_M.gguf"
GGUF_SHA256 = "183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4"
GGUF_SOURCE = "Ollama registry, library/qwen2.5:1.5b-instruct (Qwen2.5-1.5B-Instruct, Q4_K_M)"
LLM_NAME = "Qwen2.5-1.5B-Instruct, Q4_K_M GGUF"
LLM_LICENSE = "Apache-2.0"
LLAMA_CPP_VERSION = "12418 (conda-forge build cpu_mkl_h4af3a8a_0)"

TASK = (
    "Summarise the following message in two or three sentences. "
    "Write the summary in the language of the message."
)
PLACEHOLDER_RULE = (
    "The message contains placeholders in square brackets, such as [PERSON_1] or [EMAIL_1]. "
    "They stand for personal data that was removed. Whenever you refer to such a value, copy its "
    "placeholder exactly as written: same brackets, capitals, underscore and number. "
    "Do not translate, inflect, merge or invent placeholders."
)
PROMPTS = {
    "plain": TASK + "\n\nMessage:\n{text}",
    "instructed": TASK + "\n\n" + PLACEHOLDER_RULE + "\n\nMessage:\n{text}",
}


def server_executable() -> str:
    env = os.environ.get("MASKRT_LLAMA_SERVER")
    if env:
        return env
    local = Path(__file__).resolve().parent.parent / ".llama" / "Library" / "bin" / "llama-server.exe"
    if local.exists():
        return str(local)
    found = shutil.which("llama-server")
    if not found:
        raise SystemExit("llama-server not found: set MASKRT_LLAMA_SERVER or put it on PATH (see README)")
    return found


class LlamaServer:
    """Starts llama-server with the GGUF file, one slot, and stops it on exit."""

    def __init__(self, port: int = 8089, threads: int | None = None, ctx: int = 4096):
        self.port = port
        model = MODELS_DIR / GGUF_FILE
        if not model.exists():
            raise SystemExit(f"{model} is missing (see README, 'How to rerun')")
        cmd = [server_executable(), "-m", str(model), "--port", str(port), "--host", "127.0.0.1",
               "-c", str(ctx), "-np", "1", "--seed", "0", "--no-webui"]
        if threads:
            cmd += ["-t", str(threads)]
        self.cmd = cmd
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> LlamaServer:
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return self
            except OSError:
                time.sleep(0.5)
            if self.proc.poll() is not None:
                raise SystemExit("llama-server stopped while loading the model")
        raise SystemExit("llama-server did not become ready within 180 s")

    def __exit__(self, *exc) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=30)

    def chat(self, prompt: str, max_tokens: int) -> dict:
        """Greedy decoding (top_k 1, temperature 0). Returns the answer and llama.cpp's timings."""
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "top_k": 1,
            "seed": 0,
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t = time.perf_counter()
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode("utf-8"))
        wall = time.perf_counter() - t
        choice = data["choices"][0]
        timings = data.get("timings", {})
        return {
            "answer": choice["message"]["content"].strip(),
            "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens"),
            "new_tokens": data.get("usage", {}).get("completion_tokens"),
            "seconds": round(wall, 3),
            "tokens_per_second": timings.get("predicted_per_second"),
        }
