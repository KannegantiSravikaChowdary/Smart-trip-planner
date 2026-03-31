from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app

from app.services.cache_service import api_cache
from app.services.gemini_service import gemini_generate_json


WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Dense fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    95: "Thunderstorm",
}


def _fetch_json(url: str, timeout: int = 10):
    request = Request(
        url,
        headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@lru_cache(maxsize=256)
@api_cache.memoize(key_prefix="weather_coords", expiry_seconds=604800)
def _resolve_coordinates(destination: str):
    params = urlencode(
        {
            "name": destination,
            "count": 1,
            "language": "en",
            "format": "json",
        }
    )
    payload = _fetch_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}", timeout=8)
    rows = payload.get("results") or []
    if not rows:
        return None
    first = rows[0]
    lat = first.get("latitude")
    lon = first.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


@lru_cache(maxsize=1024)
@api_cache.memoize(key_prefix="openmeteo_daily", expiry_seconds=43200)
def _open_meteo_daily(destination: str, iso_date: str):
    coords = _resolve_coordinates(destination.strip().lower())
    if not coords:
        return None
    lat, lon = coords
    params = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "start_date": iso_date,
            "end_date": iso_date,
        }
    )
    payload = _fetch_json(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=10)
    daily = payload.get("daily") or {}
    codes = daily.get("weather_code") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    if not codes:
        return None
    code = int(codes[0])
    max_temp = float(max_temps[0]) if max_temps else None
    min_temp = float(min_temps[0]) if min_temps else None
    return code, min_temp, max_temp


@lru_cache(maxsize=1024)
@api_cache.memoize(key_prefix="gemini_weather", expiry_seconds=86400)
def _gemini_weather(destination: str, iso_date: str, api_key: str, model: str):
    prompt = (
        "Return only JSON object with keys: condition, min_temp_c, max_temp_c.\n"
        f"Provide a practical weather estimate for destination '{destination}' on date '{iso_date}'.\n"
        "Keep condition short (example: Partly cloudy). Temperatures in Celsius as numbers."
    )
    payload = gemini_generate_json(
        prompt=prompt,
        api_key=api_key,
        model=model,
        temperature=0.1,
        attempts=1,
        timeout_seconds=8,
    )
    if not isinstance(payload, dict):
        return None
    condition = str(payload.get("condition", "Weather update available")).strip()
    min_temp = float(payload.get("min_temp_c"))
    max_temp = float(payload.get("max_temp_c"))
    if max_temp < min_temp:
        min_temp, max_temp = max_temp, min_temp
    return condition, min_temp, max_temp


def _format_summary(iso_date: str, condition: str, min_temp: float | None, max_temp: float | None) -> str:
    if min_temp is not None and max_temp is not None:
        return f"{iso_date}: {condition}. {round(min_temp)}-{round(max_temp)} C."
    return f"{iso_date}: {condition}."


def get_live_weather(destination: str, start_date: date, day_offset: int, provider: str = "gemini") -> dict:
    target_date = start_date + timedelta(days=day_offset)
    iso_date = target_date.isoformat()
    api_key = current_app.config.get("GOOGLE_GEMINI_AI_API_KEY")
    model = current_app.config.get("GEMINI_MODEL", "gemini-flash-latest")

    providers = [provider, "open-meteo", "gemini"] if provider not in {"open-meteo", "gemini"} else [provider]
    if "open-meteo" not in providers:
        providers.append("open-meteo")
    if "gemini" not in providers:
        providers.append("gemini")

    for selected in providers:
        if selected == "open-meteo":
            try:
                weather = _open_meteo_daily(destination, iso_date)
                if weather:
                    code, min_temp, max_temp = weather
                    condition = WEATHER_CODE_LABELS.get(code, "Weather update available")
                    return {
                        "provider": "open-meteo",
                        "date": iso_date,
                        "summary": _format_summary(iso_date, condition, min_temp, max_temp),
                    }
            except Exception:
                pass

        if selected == "gemini":
            if not api_key:
                continue
            try:
                weather = _gemini_weather(destination, iso_date, api_key, model)
                if weather:
                    condition, min_temp, max_temp = weather
                    return {
                        "provider": "gemini",
                        "date": iso_date,
                        "summary": _format_summary(iso_date, condition, min_temp, max_temp),
                    }
            except Exception:
                pass

    # Last-resort, non-empty summary.
    return {
        "provider": "fallback",
        "date": iso_date,
        "summary": f"{iso_date}: Weather estimate not available now for {destination}; check again shortly.",
    }
