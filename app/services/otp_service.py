from __future__ import annotations
from datetime import datetime, timedelta
from secrets import randbelow
from threading import Lock

# In-memory store for OTPs
_OTP_STORE: dict[tuple[str, str], dict] = {}
_LOCK = Lock()

def _key(purpose: str, email: str) -> tuple[str, str]:
    """Normalize key for OTP storage"""
    return purpose.strip().lower(), email.strip().lower()

def _prune_expired(now: datetime) -> None:
    """Remove expired OTPs"""
    expired = [k for k, v in _OTP_STORE.items() if v["expires_at"] <= now]
    for k in expired:
        _OTP_STORE.pop(k, None)

def issue_otp(email: str, purpose: str, payload: dict | None = None, ttl_minutes: int = 10) -> str:
    """Generate and store OTP"""
    code = f"{randbelow(1_000_000):06d}"  # 6-digit OTP
    now = datetime.utcnow()
    record = {
        "code": code,
        "payload": payload or {},
        "expires_at": now + timedelta(minutes=max(1, ttl_minutes)),
    }
    with _LOCK:
        _prune_expired(now)
        _OTP_STORE[_key(purpose, email)] = record
    return code

def verify_otp(email: str, purpose: str, code: str) -> tuple[bool, dict]:
    """Verify OTP"""
    now = datetime.utcnow()
    with _LOCK:
        _prune_expired(now)
        key = _key(purpose, email)
        record = _OTP_STORE.get(key)
        if not record:
            return False, {"message": "OTP expired or not found."}
        if str(record["code"]).strip() != str(code).strip():
            return False, {"message": "Invalid OTP."}
        payload = record.get("payload", {})
        _OTP_STORE.pop(key, None)  # Remove OTP after successful verification
    return True, {"payload": payload}
