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


def _log_call(model: str, purpose: str | None, user_id: int | None,
              input_tokens: int, output_tokens: int, success: bool, duration_ms: int):
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO mistral_call_logs (created_at, model, purpose, user_id, input_tokens, output_tokens, success, duration_ms) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)",
            (model, purpose, user_id, input_tokens, output_tokens, int(success), duration_ms),
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

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(retries):
            t0 = time.monotonic()
            try:
                response = await client.post(MISTRAL_API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                duration_ms = int((time.monotonic() - t0) * 1000)
                usage = data.get("usage", {})
                _log_call(used_model, purpose, user_id,
                          usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                          True, duration_ms)
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException:
                _log_call(used_model, purpose, user_id, 0, 0, False,
                          int((time.monotonic() - t0) * 1000))
                if attempt == retries - 1:
                    raise
            except httpx.HTTPStatusError as e:
                _log_call(used_model, purpose, user_id, 0, 0, False,
                          int((time.monotonic() - t0) * 1000))
                if e.response.status_code >= 500 and attempt < retries - 1:
                    continue
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
