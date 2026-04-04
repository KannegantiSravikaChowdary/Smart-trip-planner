# mail_service.py
from threading import Thread
from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def _send_email_async(app, to_email: str, subject: str, body: str):
    """Send email in a background thread with Flask app context"""
    with app.app_context():  # ensures current_app works inside thread
        api_key = current_app.config.get("MAIL_PASSWORD")  # SendGrid API key
        from_email = current_app.config.get("MAIL_FROM")

        if not api_key or not from_email:
            current_app.logger.warning("SendGrid not configured")
            return

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body
        )

        try:
            sg = SendGridAPIClient(api_key)
            sg.send(message)
            current_app.logger.info("Email sent to %s", to_email)
        except Exception as e:
            current_app.logger.warning("SendGrid email failed for %s: %s", to_email, e)


def send_otp_email(to_email: str, otp: str, purpose: str, expiry_minutes: int, app):
    """Generate email content and send OTP asynchronously"""
    subject = f"{purpose.replace('_', ' ').title()} OTP - AI Air Trip Planner"
    body = (
        f"Hello,\n\n"
        f"Your OTP for {purpose.replace('_', ' ').lower()} is: {otp}\n\n"
        f"This code expires in {expiry_minutes} minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"- AI Air Trip Planner"
    )

    # Start sending in a background thread
    Thread(
        target=_send_email_async,
        args=(app, to_email, subject, body),
        daemon=True
    ).start()

    return True, "OTP email is being sent."
