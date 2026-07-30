import os
import time
from typing import Iterator

from google import genai

MODEL_ID = os.environ.get("GEMMA_MODEL_ID", "gemma-4-26b-a4b-it")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

_client = None


class ModelNotAvailableError(RuntimeError):
    pass


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GEMINI_API_KEY:
        raise ModelNotAvailableError(
            "GEMINI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/apikey"
        )
    _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _flatten_messages(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"User: {content}")
        else:
            parts.append(f"Assistant: {content}")
    parts.append("Assistant:")
    return "\n".join(parts)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "rate limit" in msg


def stream_reply(messages: list[dict]) -> Iterator[str]:
    client = _get_client()
    prompt = _flatten_messages(messages)
    last_error = None

    for attempt in range(2):
        try:
            stream = client.models.generate_content_stream(
                model=MODEL_ID,
                contents=prompt,
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as exc:
            if _is_rate_limit(exc) and attempt == 0:
                time.sleep(2)
                last_error = exc
                continue
            raise ModelNotAvailableError(str(exc)) from exc

    if last_error:
        raise ModelNotAvailableError(str(last_error)) from last_error


def load_model():
    _get_client()


def is_loaded():
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL_ID,
            contents="ping",
        )
        return response.text is not None
    except Exception:
        return False
