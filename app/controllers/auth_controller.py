import json
import secrets
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User
from app.services.email_service import send_otp_email
from app.services.otp_service import issue_otp, verify_otp
from app.services.validation_service import (
    email_domain_resolves,
    is_valid_email,
    is_valid_full_name,
    is_valid_phone,
    normalize_email,
    password_strength_errors,
)


auth_bp = Blueprint("auth", __name__)


def _google_post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    body = urlencode(payload).encode("utf-8")
    request_obj = Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request_obj, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _google_get_json(url: str, access_token: str, timeout: int = 15) -> dict:
    request_obj = Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urlopen(request_obj, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    otp_expiry_minutes = int(current_app.config.get("OTP_EXPIRY_MINUTES", 10) or 10)

    if request.method == "POST":
        action = request.form.get("action", "send_register_otp").strip().lower()

        if action == "send_register_otp":
            full_name = request.form.get("full_name", "").strip()
            email = normalize_email(request.form.get("email", ""))
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            phone = request.form.get("phone", "").strip()
            whatsapp_opt_in = True
            role = request.form.get("role", "traveler").lower()

            if role not in {"traveler", "agent"}:
                flash("Invalid role selected.", "danger")
                return redirect(url_for("auth.register"))

            if not full_name or not email or not password:
                flash("All fields are required.", "danger")
                return redirect(url_for("auth.register"))

            if not is_valid_full_name(full_name):
                flash("Enter a valid full name (letters only, min 2 chars).", "danger")
                return redirect(url_for("auth.register"))

            if not is_valid_email(email):
                flash("Enter a valid email address (example: user@example.com).", "danger")
                return redirect(url_for("auth.register"))
            if not email_domain_resolves(email):
                flash("Email domain is not reachable. Please use a valid inbox domain.", "danger")
                return redirect(url_for("auth.register"))
            if not phone:
                flash("Phone number is required.", "danger")
                return redirect(url_for("auth.register"))
            if not is_valid_phone(phone):
                flash("Enter a valid phone number with country code.", "danger")
                return redirect(url_for("auth.register"))

            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return redirect(url_for("auth.register"))

            password_errors = password_strength_errors(password)
            if password_errors:
                flash(f"Password must include {', '.join(password_errors)}.", "danger")
                return redirect(url_for("auth.register"))

            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "warning")
                return redirect(url_for("auth.register"))

            otp = issue_otp(
                email=email,
                purpose="register",
                payload={
                    "full_name": full_name,
                    "email": email,
                    "password": password,
                    "role": role,
                    "phone": phone,
                    "whatsapp_opt_in": whatsapp_opt_in,
                    "auth_method": "manual",
                },
                ttl_minutes=otp_expiry_minutes,
            )
            sent, message = send_otp_email(email, otp, "registration", otp_expiry_minutes)
            if not sent:
                flash(message, "danger")
                return redirect(url_for("auth.register"))

            flash("OTP sent to your email. Verify to complete registration.", "info")
            return render_template("auth/register.html", otp_required=True, otp_email=email)

        if action == "verify_register_otp":
            email = normalize_email(request.form.get("email", ""))
            otp = request.form.get("otp", "").strip()
            if not email or not otp:
                flash("Email and OTP are required.", "danger")
                return render_template("auth/register.html", otp_required=True, otp_email=email)

            is_verified, result = verify_otp(email=email, purpose="register", code=otp)
            if not is_verified:
                flash(result.get("message", "OTP verification failed."), "danger")
                return render_template("auth/register.html", otp_required=True, otp_email=email)

            payload = result.get("payload", {})
            full_name = payload.get("full_name", "").strip()
            role = payload.get("role", "traveler").strip().lower()
            password = payload.get("password", "")
            phone = payload.get("phone", "").strip()
            whatsapp_opt_in = bool(payload.get("whatsapp_opt_in", True))
            auth_method = str(payload.get("auth_method", "manual")).strip().lower()
            google_sub = str(payload.get("google_sub", "")).strip()

            if role not in {"traveler", "agent"}:
                role = "traveler"

            if not full_name:
                flash("Registration session expired. Please register again.", "danger")
                return redirect(url_for("auth.register"))

            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "warning")
                return redirect(url_for("auth.login"))

            user = User(
                full_name=full_name,
                email=email,
                role=role,
                phone=phone or None,
                whatsapp_opt_in=whatsapp_opt_in,
                google_sub=google_sub or None,
            )
            if auth_method == "google":
                user.set_password(secrets.token_urlsafe(24))
            else:
                if not password:
                    flash("Registration session expired. Please register again.", "danger")
                    return redirect(url_for("auth.register"))
                user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash("Account created successfully. Please login.", "success")
            return redirect(url_for("auth.login"))

        flash("Invalid registration request.", "danger")
        return redirect(url_for("auth.register"))

    return render_template("auth/register.html", otp_required=False, otp_email="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        whatsapp_opt_in = True
        remember = bool(request.form.get("remember"))

        if not is_valid_email(email):
            flash("Invalid email format.", "danger")
            return redirect(url_for("auth.login"))
        if not phone:
            flash("Phone number is required.", "danger")
            return redirect(url_for("auth.login"))
        if not is_valid_phone(phone):
            flash("Enter a valid phone number with country code.", "danger")
            return redirect(url_for("auth.login"))

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.login"))

        if phone:
            user.phone = phone
            user.whatsapp_opt_in = whatsapp_opt_in
            db.session.commit()

        login_user(user, remember=remember)
        flash("Welcome back.", "success")

        if user.role == "agent":
            return redirect(url_for("agent.dashboard"))
        return redirect(url_for("traveler.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    otp_expiry_minutes = int(current_app.config.get("OTP_EXPIRY_MINUTES", 10) or 10)

    if request.method == "POST":
        action = request.form.get("action", "send_forgot_otp").strip().lower()

        if action == "send_forgot_otp":
            email = normalize_email(request.form.get("email", ""))
            if not is_valid_email(email):
                flash("Enter a valid email address.", "danger")
                return redirect(url_for("auth.forgot_password"))

            user = User.query.filter_by(email=email).first()
            if user:
                otp = issue_otp(
                    email=email,
                    purpose="forgot_password",
                    payload={"user_id": user.id},
                    ttl_minutes=otp_expiry_minutes,
                )
                sent, message = send_otp_email(email, otp, "password reset", otp_expiry_minutes)
                if not sent:
                    flash(message, "danger")
                    return redirect(url_for("auth.forgot_password"))

            # Keep response generic to avoid user enumeration.
            flash("If the email is registered, an OTP has been sent.", "info")
            return render_template("auth/forgot_password.html", otp_required=True, otp_email=email)

        if action == "reset_password":
            email = normalize_email(request.form.get("email", ""))
            otp = request.form.get("otp", "").strip()
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not (email and otp and new_password and confirm_password):
                flash("All fields are required.", "danger")
                return render_template("auth/forgot_password.html", otp_required=True, otp_email=email)

            if new_password != confirm_password:
                flash("Passwords do not match.", "danger")
                return render_template("auth/forgot_password.html", otp_required=True, otp_email=email)

            password_errors = password_strength_errors(new_password)
            if password_errors:
                flash(f"Password must include {', '.join(password_errors)}.", "danger")
                return render_template("auth/forgot_password.html", otp_required=True, otp_email=email)

            is_verified, result = verify_otp(email=email, purpose="forgot_password", code=otp)
            if not is_verified:
                flash(result.get("message", "OTP verification failed."), "danger")
                return render_template("auth/forgot_password.html", otp_required=True, otp_email=email)

            payload = result.get("payload", {})
            user_id = payload.get("user_id")
            user = User.query.get(user_id) if user_id else None
            if not user or normalize_email(user.email) != email:
                flash("Unable to reset password. Please restart forgot password flow.", "danger")
                return redirect(url_for("auth.forgot_password"))

            user.set_password(new_password)
            db.session.commit()
            flash("Password reset successful. Please login with your new password.", "success")
            return redirect(url_for("auth.login"))

        flash("Invalid forgot-password request.", "danger")
        return redirect(url_for("auth.forgot_password"))

    return render_template("auth/forgot_password.html", otp_required=False, otp_email="")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/profile")
@login_required
def profile():
    return render_template("auth/profile.html")


@auth_bp.route("/profile/update", methods=["POST"])
@login_required
def update_profile():
    phone = request.form.get("phone", "").strip()
    if not phone or not is_valid_phone(phone):
        flash("Enter a valid phone number with country code.", "danger")
        return redirect(url_for("auth.profile"))

    current_user.phone = phone
    db.session.commit()
    flash("Profile updated.", "success")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/google/start")
def google_start():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    client_id = current_app.config.get("GOOGLE_AUTH_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_AUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        flash("Google authentication is not configured.", "danger")
        return redirect(url_for("auth.login"))

    mode = (request.args.get("mode", "login") or "login").strip().lower()
    if mode not in {"login", "register"}:
        mode = "login"

    role = (request.args.get("role", "traveler") or "traveler").strip().lower()
    if role not in {"traveler", "agent"}:
        role = "traveler"

    state = secrets.token_urlsafe(24)
    session["google_oauth"] = {"state": state, "mode": mode, "role": role}
    redirect_uri = current_app.config.get("GOOGLE_AUTH_REDIRECT_URI") or url_for("auth.google_callback", _external=True)
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@auth_bp.route("/google/callback")
def google_callback():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    oauth_session = session.pop("google_oauth", {}) or {}
    expected_state = oauth_session.get("state")
    mode = str(oauth_session.get("mode", "login")).strip().lower()
    role = str(oauth_session.get("role", "traveler")).strip().lower()
    if mode not in {"login", "register"}:
        mode = "login"
    if role not in {"traveler", "agent"}:
        role = "traveler"
    received_state = request.args.get("state", "")
    if not expected_state or received_state != expected_state:
        flash("Google authentication state mismatch. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    code = request.args.get("code", "").strip()
    if not code:
        flash("Google authentication failed: missing authorization code.", "danger")
        return redirect(url_for("auth.login"))

    client_id = current_app.config.get("GOOGLE_AUTH_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_AUTH_CLIENT_SECRET")
    redirect_uri = current_app.config.get("GOOGLE_AUTH_REDIRECT_URI") or url_for("auth.google_callback", _external=True)
    try:
        token_payload = _google_post_json(
            "https://oauth2.googleapis.com/token",
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise ValueError("Missing access token.")
        profile = _google_get_json("https://openidconnect.googleapis.com/v1/userinfo", access_token=access_token)
    except Exception as exc:
        current_app.logger.warning("Google OAuth callback failed: %s", exc)
        flash("Google sign-in failed. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    email = normalize_email(profile.get("email", ""))
    full_name = str(profile.get("name", "")).strip() or "Google User"
    google_sub = str(profile.get("sub", "")).strip()
    email_verified = bool(profile.get("email_verified"))
    if not email or not email_verified:
        flash("Google account email is not verified.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(google_sub=google_sub).first() if google_sub else None
    if not user:
        user = User.query.filter_by(email=email).first()

    if mode == "login":
        if not user:
            flash("Google account is not registered. Please sign up first.", "warning")
            return redirect(url_for("auth.register"))

        if not user.google_sub and google_sub:
            user.google_sub = google_sub
        if not user.full_name and full_name:
            user.full_name = full_name
        db.session.commit()

        login_user(user, remember=True)
        if not user.phone:
            flash("Please add your phone number to enable WhatsApp notifications.", "warning")
            return redirect(url_for("auth.profile"))
        flash("Signed in with Google.", "success")
        if user.role == "agent":
            return redirect(url_for("agent.dashboard"))
        return redirect(url_for("traveler.dashboard"))

    # register mode: do not log in directly; require OTP verification.
    if user:
        flash("This Google email is already registered. Please sign in.", "info")
        return redirect(url_for("auth.login"))

    otp_expiry_minutes = int(current_app.config.get("OTP_EXPIRY_MINUTES", 10) or 10)
    otp = issue_otp(
        email=email,
        purpose="register",
        payload={
            "full_name": full_name,
            "email": email,
            "role": role,
            "phone": "",
            "whatsapp_opt_in": True,
            "auth_method": "google",
            "google_sub": google_sub,
        },
        ttl_minutes=otp_expiry_minutes,
    )
    sent, message = send_otp_email(email, otp, "registration", otp_expiry_minutes)
    if not sent:
        flash(message, "danger")
        return redirect(url_for("auth.register"))

    flash("Google verified. OTP sent to your email. Verify to complete signup.", "info")
    return render_template("auth/register.html", otp_required=True, otp_email=email)
