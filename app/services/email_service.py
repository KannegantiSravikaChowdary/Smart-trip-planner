from __future__ import annotations
from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def send_plain_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:

    api_key = current_app.config.get("SENDGRID_API_KEY")
    from_email = current_app.config.get("MAIL_FROM")

    if not api_key or not from_email:
        return False, "Email configuration missing."

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body
    )

    try:
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        return True, "Email sent successfully."

    except Exception as e:
        current_app.logger.error(f"Email send failed: {e}")
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
