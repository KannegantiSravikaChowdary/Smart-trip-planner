import smtplib
from email.message import EmailMessage
from flask import current_app


def send_otp_email(email, otp, purpose, expiry_minutes):
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Your OTP for {purpose}"
        msg["From"] = current_app.config.get("MAIL_USERNAME")
        msg["To"] = email

        msg.set_content(
            f"""
Your OTP for {purpose} is: {otp}

This OTP will expire in {expiry_minutes} minutes.

If you did not request this, please ignore this email.
"""
        )

        host = current_app.config.get("MAIL_HOST")
        port = int(current_app.config.get("MAIL_PORT", 587))
        username = current_app.config.get("MAIL_USERNAME")
        password = current_app.config.get("MAIL_PASSWORD")
        use_tls = str(current_app.config.get("MAIL_USE_TLS", "True")).lower() == "true"

        server = smtplib.SMTP(host, port)

        if use_tls:
            server.starttls()

        server.login(username, password)
        server.send_message(msg)
        server.quit()

        return True, "OTP sent successfully"

    except Exception as e:
        current_app.logger.error(f"Email sending failed: {e}")
        return False, "Unable to send email right now. Please try again."
