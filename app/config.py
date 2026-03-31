import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _clean_env_value(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower().startswith("replace-with"):
        return None
    return normalized


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    INSTANCE_DIR = BASE_DIR / "instance"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads", "payments")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
    _RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///instance/air_trip_planner.db")
    if _RAW_DATABASE_URL.startswith("sqlite:///") and not _RAW_DATABASE_URL.startswith("sqlite:////"):
        _sqlite_rel_path = _RAW_DATABASE_URL.replace("sqlite:///", "", 1)
        _DATABASE_URI = f"sqlite:///{(BASE_DIR / _sqlite_rel_path).resolve().as_posix()}"
    else:
        _DATABASE_URI = _RAW_DATABASE_URL
    SQLALCHEMY_DATABASE_URI = _DATABASE_URI
    SQLALCHEMY_ENGINE_OPTIONS = (
        {
            "connect_args": {
                "timeout": 60,
                "check_same_thread": False,
            }
        }
        if _DATABASE_URI.startswith("sqlite")
        else {}
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    _RAW_MODEL_PATH = os.getenv("MODEL_PATH", "ml/budget_model.joblib")
    MODEL_PATH = str((BASE_DIR / _RAW_MODEL_PATH).resolve()) if not Path(_RAW_MODEL_PATH).is_absolute() else _RAW_MODEL_PATH
    # Accept both backend-style and Vite-style env names for local convenience.
    GOOGLE_PLACES_API_KEY = _clean_env_value(os.getenv("GOOGLE_PLACES_API_KEY")) or _clean_env_value(
        os.getenv("VITE_GOOGLE_PLACES_API_KEY")
    )
    GOOGLE_GEMINI_AI_API_KEY = _clean_env_value(os.getenv("GOOGLE_GEMINI_AI_API_KEY")) or _clean_env_value(
        os.getenv("VITE_GOOGLE_GEMINI_AI_API_KEY")
    )
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    GOOGLE_AUTH_CLIENT_ID = _clean_env_value(os.getenv("GOOGLE_AUTH_CLIENT_ID")) or _clean_env_value(
        os.getenv("VITE_GOOGLE_AUTH_CLIENT_ID")
    )
    GOOGLE_AUTH_CLIENT_SECRET = _clean_env_value(os.getenv("GOOGLE_AUTH_CLIENT_SECRET"))
    GOOGLE_AUTH_REDIRECT_URI = _clean_env_value(os.getenv("GOOGLE_AUTH_REDIRECT_URI"))
    WEATHER_PROVIDER = os.getenv("WEATHER_PROVIDER", "open-meteo")
    HOTEL_PROVIDER = os.getenv("HOTEL_PROVIDER", "rapidapi")
    RAPIDAPI_KEY = _clean_env_value(os.getenv("RAPIDAPI_KEY")) or _clean_env_value(os.getenv("X_RAPIDAPI_KEY"))
    RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "booking-com.p.rapidapi.com")
    RAPIDAPI_TIMEOUT_SECONDS = int(os.getenv("RAPIDAPI_TIMEOUT_SECONDS", "15"))
    RAPIDAPI_LOCALE = os.getenv("RAPIDAPI_LOCALE", "en-us")
    RAPIDAPI_CURRENCY = os.getenv("RAPIDAPI_CURRENCY", "INR")
    MAIL_HOST = _clean_env_value(os.getenv("MAIL_HOST"))
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = _clean_env_value(os.getenv("MAIL_USERNAME"))
    MAIL_PASSWORD = _clean_env_value(os.getenv("MAIL_PASSWORD"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
    MAIL_FROM = _clean_env_value(os.getenv("MAIL_FROM"))
    OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000").strip()
    TWILIO_ACCOUNT_SID = _clean_env_value(os.getenv("TWILIO_ACCOUNT_SID"))
    TWILIO_AUTH_TOKEN = _clean_env_value(os.getenv("TWILIO_AUTH_TOKEN"))
    TWILIO_WHATSAPP_FROM = _clean_env_value(os.getenv("TWILIO_WHATSAPP_FROM"))
    TWILIO_CONTENT_SID = _clean_env_value(os.getenv("TWILIO_CONTENT_SID"))
    TWILIO_TEMPLATE_TIME = os.getenv("TWILIO_TEMPLATE_TIME", "3pm").strip()
    TWILIO_TIMEOUT_SECONDS = int(os.getenv("TWILIO_TIMEOUT_SECONDS", "12"))
    _RAW_FOOD_DATASET_PATH = os.getenv("FOOD_DATASET_PATH", "data/food_cost_dataset.csv")
    FOOD_DATASET_PATH = (
        str((BASE_DIR / _RAW_FOOD_DATASET_PATH).resolve())
        if not Path(_RAW_FOOD_DATASET_PATH).is_absolute()
        else _RAW_FOOD_DATASET_PATH
    )
    _RAW_FOOD_MODEL_PATH = os.getenv("FOOD_MODEL_PATH", "ml/food_cost_model.joblib")
    FOOD_MODEL_PATH = (
        str((BASE_DIR / _RAW_FOOD_MODEL_PATH).resolve())
        if not Path(_RAW_FOOD_MODEL_PATH).is_absolute()
        else _RAW_FOOD_MODEL_PATH
    )
