from flask import session
from datetime import datetime, timedelta
import random

SESSION_KEY = "otp_data"

def issue_otp(email: str, purpose: str, ttl_minutes: int = 5) -> str:
    code = f"{random.randint(0, 999999):06d}"
    session[SESSION_KEY] = {
        "email": email.lower(),
        "purpose": purpose.lower(),
        "code": code,
        "expires_at": (datetime.utcnow() + timedelta(minutes=ttl_minutes)).timestamp()
    }
    return code

def verify_otp(email: str, purpose: str, code: str) -> tuple[bool, dict]:
    otp_record = session.get(SESSION_KEY)
    if not otp_record:
        return False, {"message": "OTP expired or not found."}
    if otp_record["email"] != email.lower() or otp_record["purpose"] != purpose.lower():
        return False, {"message": "Invalid OTP."}
    if otp_record["code"] != code.strip():
        return False, {"message": "Invalid OTP."}
    if datetime.utcnow().timestamp() > otp_record["expires_at"]:
        return False, {"message": "OTP expired."}
    session.pop(SESSION_KEY)
    return True, {"payload": {}}
