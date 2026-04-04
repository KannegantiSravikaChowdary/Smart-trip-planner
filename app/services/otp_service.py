from __future__ import annotations

from datetime import datetime, timedelta
from secrets import randbelow
from threading import Lock


_STORE: dict[tuple[str, str], dict] = {}
_LOCK = Lock()


def _key(purpose: str, email: str) -> tuple[str, str]:
    return purpose.strip().lower(), email.strip().lower()


def _prune_expired(now: datetime) -> None:
    expired_keys = [item_key for item_key, data in _STORE.items() if data["expires_at"] <= now]
    for item_key in expired_keys:
        _STORE.pop(item_key, None)


def issue_otp(email: str, purpose: str, payload: dict | None = None, ttl_minutes: int = 10) -> str:
    code = f"{randbelow(1_000_000):06d}"
    now = datetime.utcnow()
    record = {
        "code": code,
        "payload": payload or {},
        "expires_at": now + timedelta(minutes=max(1, ttl_minutes)),
    }
    with _LOCK:
        _prune_expired(now)
        _STORE[_key(purpose, email)] = record
    return code


def verify_otp(email: str, purpose: str, code: str) -> tuple[bool, dict]:
    now = datetime.utcnow()
    with _LOCK:
        _prune_expired(now)
        item_key = _key(purpose, email)
        record = _STORE.get(item_key)
        if not record:
            return False, {"message": "OTP expired or not found."}
        if str(record["code"]).strip() != str(code).strip():
            return False, {"message": "Invalid OTP."}
        payload = record.get("payload", {})
        _STORE.pop(item_key, None)
    return True, {"payload": payload}
