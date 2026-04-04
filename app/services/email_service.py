from __future__ import annotations
import smtplib
from email.message import EmailMessage
from flask import current_app


def _mail_config() -> dict:
    return {
        "host": current_app.config.get("MAIL_HOST"),
        "port": int(current_app.config.get("MAIL_PORT", 587)),
        "username": current_app.config.get("MAIL_USERNAME"),
        "password": current_app.config.get("MAIL_PASSWORD"),
        "use_tls": str(current_app.config.get("MAIL_USE_TLS", "True")).lower() == "true",
        "from_email": current_app.config.get("MAIL_FROM"),
    }


def send_plain_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    config = _mail_config()

    if not all([config["host"], config["port"], config["username"], config["password"], config["from_email"]]):
        return False, "Email configuration missing."

    msg = EmailMessage()
    msg["From"] = config["from_email"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as smtp:
            if config["use_tls"]:
                smtp.starttls()

            smtp.login(config["username"], config["password"])
            smtp.send_message(msg)

        return True, "Email sent successfully."

    except Exception as exc:
        current_app.logger.error(f"Email send failed: {exc}")
        return False, "Unable to send email right now. Please try again."


def send_otp_email(to_email: str, otp: str, purpose: str, expiry_minutes: int) -> tuple[bool, str]:
    pretty_purpose = purpose.replace("_", " ").title()

    subject = f"{pretty_purpose} OTP - AI Air Trip Planner"

    body = f"""
Hello,

Your OTP for {pretty_purpose.lower()} is: {otp}

This code expires in {expiry_minutes} minutes.

If you did not request this, please ignore this email.

- AI Air Trip Planner
"""

    return send_plain_email(to_email, subject, body)
