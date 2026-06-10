import asyncio
import httpx
import json
import os
import sqlite3
import time
from typing import List, Dict, Any, Optional

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "politrain.db")

# Limit concurrent Mistral calls to avoid rate limiting when many batches fire at once
_API_SEMAPHORE = asyncio.Semaphore(3)

# Mistral enforces a requests-per-second limit (429 code 1300). The semaphore allows
# 3 concurrent calls but they all START simultaneously → instant 429 → fallback to small
# (worse quality). Space out request starts globally; in-flight requests still overlap.
_PACE_LOCK = asyncio.Lock()
_MIN_REQUEST_INTERVAL = 1.0  # seconds between request starts
_last_request_at = 0.0


async def _pace_request():
    global _last_request_at
    async with _PACE_LOCK:
        wait = _last_request_at + _MIN_REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


def _log_call(model: str, purpose: str | None, user_id: int | None,
              input_tokens: int, output_tokens: int, success: bool, duration_ms: int,
              error_message: str | None = None):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO mistral_call_logs "
            "(created_at, model, purpose, user_id, input_tokens, output_tokens, success, duration_ms, error_message) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)",
            (model, purpose, user_id, input_tokens, output_tokens, int(success), duration_ms, error_message),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


async def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: float = 30.0,
    retries: int = 3,
    model: Optional[str] = None,
    purpose: Optional[str] = None,
    user_id: Optional[int] = None,
) -> str:
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not set")

    used_model = model or MISTRAL_MODEL
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": used_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with _API_SEMAPHORE:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(retries):
                await _pace_request()
                t0 = time.monotonic()
                try:
                    response = await client.post(MISTRAL_API_URL, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    usage = data.get("usage", {})
                    choice = data["choices"][0]
                    finish_reason = choice.get("finish_reason")
                    content = choice["message"]["content"]
                    if finish_reason == "content_filter" or (
                        isinstance(content, str) and "blocked by content filtering" in content.lower()
                    ):
                        _log_call(used_model, purpose, user_id, 0, 0, False, duration_ms,
                                  "content_filter")
                        raise RuntimeError("content_filter")
                    _log_call(used_model, purpose, user_id,
                              usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                              True, duration_ms)
                    return content
                except httpx.TimeoutException as e:
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    _log_call(used_model, purpose, user_id, 0, 0, False, duration_ms,
                              f"timeout after {duration_ms}ms")
                    if attempt == retries - 1:
                        raise
                except httpx.HTTPStatusError as e:
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    err_body = ""
                    try:
                        err_body = e.response.text[:200]
                    except Exception:
                        pass
                    _log_call(used_model, purpose, user_id, 0, 0, False, duration_ms,
                              f"HTTP {e.response.status_code}: {err_body}")
                    status = e.response.status_code
                    if attempt < retries - 1:
                        if status == 429:
                            await asyncio.sleep(2 ** (attempt + 1))
                            continue
                        if status >= 500:
                            await asyncio.sleep(1)
                            continue
                    raise
                except Exception as e:
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    _log_call(used_model, purpose, user_id, 0, 0, False, duration_ms,
                              f"{type(e).__name__}: {str(e)[:200]}")
                    raise

    raise RuntimeError("Failed after retries")


async def simple_prompt(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: float = 30.0,
    retries: int = 3,
    model: Optional[str] = None,
    purpose: Optional[str] = None,
    user_id: Optional[int] = None,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return await chat_completion(
        messages, temperature=temperature, max_tokens=max_tokens,
        timeout=timeout, retries=retries, model=model,
        purpose=purpose, user_id=user_id,
    )


async def parse_json_response(text: str) -> Any:
    import re
    text = text.strip()
    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Extract first JSON array or object from response (handles extra text around JSON)
        match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', text)
        if match:
            return json.loads(match.group(1))
        raise
