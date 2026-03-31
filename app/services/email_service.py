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
        "use_tls": bool(current_app.config.get("MAIL_USE_TLS", True)),
        "from_email": current_app.config.get("MAIL_FROM"),
    }


def send_plain_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    config = _mail_config()

    if not (config["host"] and config["port"] and config["username"] and config["password"] and config["from_email"]):
        return False, "Email server is not configured. Set MAIL_* environment variables."

    msg = EmailMessage()
    msg["From"] = config["from_email"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=15) as smtp:
            if config["use_tls"]:
                smtp.starttls()
            smtp.login(config["username"], config["password"])
            smtp.send_message(msg)

        return True, "Email sent."

    except Exception as exc:
        current_app.logger.warning("Email send failed for %s: %s", to_email, exc)
        return False, "Unable to send email right now. Please try again."
