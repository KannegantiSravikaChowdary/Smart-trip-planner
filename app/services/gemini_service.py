from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.request import urlopen


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    return "\n".join((part.get("text") or "") for part in parts).strip()


def _strip_code_fence(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()


def _load_json_from_text(text: str):
    cleaned = _strip_code_fence(text)
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Best-effort extraction for model responses with surrounding prose.
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def gemini_generate_json(
    prompt: str,
    api_key: str,
    model: str = "gemini-flash-latest",
    temperature: float = 0.2,
    attempts: int = 2,
    timeout_seconds: int = 12,
):
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{urlencode({'key': api_key})}"
    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    body = json.dumps(request_body).encode("utf-8")

    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            request = Request(
                endpoint,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)",
                },
                method="POST",
            )
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = _extract_text(payload)
            result = _load_json_from_text(text)
            return result
        except (TimeoutError, URLError, HTTPError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
    
    return None


def gemini_generate_text(
    prompt: str,
    api_key: str,
    model: str = "gemini-flash-latest",
    temperature: float = 0.4,
    attempts: int = 2,
    timeout_seconds: int = 12,
) -> str:
    result = gemini_generate_text_result(
        prompt=prompt,
        api_key=api_key,
        model=model,
        temperature=temperature,
        attempts=attempts,
        timeout_seconds=timeout_seconds,
    )
    return result.get("text", "")


def gemini_generate_text_result(
    prompt: str,
    api_key: str,
    model: str = "gemini-flash-latest",
    temperature: float = 0.4,
    attempts: int = 2,
    timeout_seconds: int = 12,
) -> dict:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{urlencode({'key': api_key})}"
    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }
    body = json.dumps(request_body).encode("utf-8")

    for attempt in range(max(1, attempts)):
        try:
            request = Request(
                endpoint,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)",
                },
                method="POST",
            )
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = _extract_text(payload)
            return {
                "text": text.strip(),
                "error": "",
                "status_code": None,
            }
        except HTTPError as exc:
            error_payload = ""
            try:
                error_payload = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                error_payload = ""
            error_message = ""
            if error_payload:
                try:
                    parsed = json.loads(error_payload)
                    error_message = (
                        parsed.get("error", {}).get("message")
                        or parsed.get("error", {}).get("status")
                        or ""
                    ).strip()
                except json.JSONDecodeError:
                    error_message = error_payload.strip()
            if not error_message:
                error_message = str(exc).strip()

            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            return {
                "text": "",
                "error": error_message,
                "status_code": int(getattr(exc, "code", 0) or 0),
            }
        except (TimeoutError, URLError, json.JSONDecodeError) as exc:
            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            return {
                "text": "",
                "error": str(exc).strip() or "Chat service request failed.",
                "status_code": None,
            }

    return {
        "text": "",
        "error": "Chat service request failed.",
        "status_code": None,
    }
