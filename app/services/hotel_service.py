import concurrent.futures
from flask import current_app
from sqlalchemy import func
from types import SimpleNamespace
import math

from app.extensions import db
from app.models import Hotel
from app.services.place_service import fetch_live_hotels


def run_in_context(app, func, *args, **kwargs):
    with app.app_context():
        return func(*args, **kwargs)


def _upsert_live_hotel(hotel_data: dict) -> Hotel:
    name = (hotel_data.get("name") or "").strip()
    city = (hotel_data.get("city") or "").strip()
    existing = (
        Hotel.query.filter(func.lower(Hotel.name) == name.lower(), func.lower(Hotel.city) == city.lower()).first()
        if name and city
        else None
    )
    if existing:
        existing.address = hotel_data["address"]
        existing.price_min = hotel_data["price_min"]
        existing.price_max = hotel_data["price_max"]
        existing.rating = hotel_data["rating"]
        existing.distance_km = hotel_data["distance_km"]
        existing.map_link = hotel_data["map_link"]
        return existing

    hotel = Hotel(
        name=hotel_data["name"],
        city=hotel_data["city"],
        address=hotel_data["address"],
        price_min=hotel_data["price_min"],
        price_max=hotel_data["price_max"],
        rating=hotel_data["rating"],
        distance_km=hotel_data["distance_km"],
        map_link=hotel_data["map_link"],
    )
    db.session.add(hotel)
    return hotel


def _to_hotel_like(hotel_data: dict):
    return SimpleNamespace(
        id=None,
        name=hotel_data["name"],
        city=hotel_data["city"],
        address=hotel_data["address"],
        price_min=hotel_data["price_min"],
        price_max=hotel_data["price_max"],
        rating=hotel_data["rating"],
        distance_km=hotel_data["distance_km"],
        map_link=hotel_data["map_link"],
        availability_status=hotel_data.get("availability_status", "Live status unavailable"),
        rooms_available=hotel_data.get("rooms_available"),
    )


def _normalize_destinations(destinations: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for destination in destinations:
        city = (destination or "").strip()
        if not city:
            continue
        key = city.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(city)
    return normalized


def _hotel_key(hotel) -> str:
    return f"{str(hotel.name).strip().lower()}::{str(hotel.city).strip().lower()}"


def _round_robin_hotels(destinations: list[str], pools_by_city: dict[str, list], limit: int) -> list:
    selected = []
    selected_keys: set[str] = set()
    round_idx = 0

    while len(selected) < limit:
        added_this_round = False
        for city in destinations:
            city_pool = pools_by_city.get(city.lower(), [])
            if round_idx >= len(city_pool):
                continue
            hotel = city_pool[round_idx]
            key = _hotel_key(hotel)
            if key in selected_keys:
                continue
            selected.append(hotel)
            selected_keys.add(key)
            added_this_round = True
            if len(selected) >= limit:
                break
        if not added_this_round:
            break
        round_idx += 1

    return selected


def _top_up_with_remaining(selected: list, pools_by_city: dict[str, list], limit: int) -> list:
    selected_keys = {_hotel_key(hotel) for hotel in selected}
    for city_hotels in pools_by_city.values():
        for hotel in city_hotels:
            key = _hotel_key(hotel)
            if key in selected_keys:
                continue
            selected.append(hotel)
            selected_keys.add(key)
            if len(selected) >= limit:
                return selected
    return selected


def recommended_hotels(
    destinations: list[str],
    state_country: str | None = None,
    limit: int = 6,
    persist: bool = False,
    checkin_date: str | None = None,
    checkout_date: str | None = None,
):
    city_list = _normalize_destinations(destinations)
    if not city_list:
        return []

    limit = max(1, int(limit or 1))
    per_city_limit = max(1, math.ceil(limit / len(city_list)))
    fetch_limit = max(3, per_city_limit + 1)

    provider = current_app.config.get("HOTEL_PROVIDER", "rapidapi")
    gemini_api_key = current_app.config.get("GOOGLE_GEMINI_AI_API_KEY")
    places_api_key = current_app.config.get("GOOGLE_PLACES_API_KEY")
    gemini_model = current_app.config.get("GEMINI_MODEL", "gemini-flash-latest")
    rapidapi_key = current_app.config.get("RAPIDAPI_KEY")
    rapidapi_host = current_app.config.get("RAPIDAPI_HOST", "booking-com.p.rapidapi.com")
    rapidapi_locale = current_app.config.get("RAPIDAPI_LOCALE", "en-us")
    rapidapi_currency = current_app.config.get("RAPIDAPI_CURRENCY", "INR")
    rapidapi_timeout = int(current_app.config.get("RAPIDAPI_TIMEOUT_SECONDS", 15) or 15)
    pools_by_city: dict[str, list] = {}

    app = current_app._get_current_object()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(city_list))) as executor:
        futures = {}
        for city in city_list:
            futures[city] = executor.submit(
                run_in_context,
                app,
                fetch_live_hotels,
                city,
                state_country=state_country,
                api_key=gemini_api_key,
                places_api_key=places_api_key,
                model=gemini_model,
                limit=fetch_limit,
                provider=provider,
                rapidapi_key=rapidapi_key,
                rapidapi_host=rapidapi_host,
                rapidapi_locale=rapidapi_locale,
                rapidapi_currency=rapidapi_currency,
                rapidapi_timeout=rapidapi_timeout,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
            )
            
        for city, future in futures.items():
            city_hotels = []
            live_rows = future.result()
            for row in live_rows:
                hotel = _upsert_live_hotel(row) if persist else _to_hotel_like(row)
                setattr(hotel, "availability_status", row.get("availability_status", "Live status unavailable"))
                setattr(hotel, "rooms_available", row.get("rooms_available"))
                city_hotels.append(hotel)
            pools_by_city[city.lower()] = city_hotels

    if any(pools_by_city.values()):
        # Top up each destination from DB cache if live provider returned fewer hotels for that city.
        for city in city_list:
            city_key = city.lower()
            city_hotels = pools_by_city.get(city_key, [])
            existing_keys = {_hotel_key(hotel) for hotel in city_hotels}
            if len(city_hotels) < per_city_limit:
                cached = (
                    Hotel.query.filter(func.lower(Hotel.city) == city_key)
                    .order_by(Hotel.rating.desc())
                    .limit(fetch_limit)
                    .all()
                )
                for item in cached:
                    key = _hotel_key(item)
                    if key in existing_keys:
                        continue
                    setattr(item, "availability_status", getattr(item, "availability_status", "Live status unavailable"))
                    setattr(item, "rooms_available", getattr(item, "rooms_available", None))
                    city_hotels.append(item)
                    existing_keys.add(key)
                    if len(city_hotels) >= per_city_limit:
                        break
            pools_by_city[city_key] = city_hotels

        selected = _round_robin_hotels(city_list, pools_by_city, limit)
        selected = _top_up_with_remaining(selected, pools_by_city, limit)
        if persist:
            db.session.commit()
        return selected[:limit]

    # Graceful fallback to existing DB cache if live provider is unavailable.
    cached_pools: dict[str, list] = {}
    for city in city_list:
        cached_pools[city.lower()] = (
            Hotel.query.filter(func.lower(Hotel.city) == city.lower())
            .order_by(Hotel.rating.desc())
            .limit(fetch_limit)
            .all()
        )
        for item in cached_pools[city.lower()]:
            setattr(item, "availability_status", getattr(item, "availability_status", "Live status unavailable"))
            setattr(item, "rooms_available", getattr(item, "rooms_available", None))
    if any(cached_pools.values()):
        selected = _round_robin_hotels(city_list, cached_pools, limit)
        selected = _top_up_with_remaining(selected, cached_pools, limit)
        return selected[:limit]

    # Do not fallback to unrelated global hotels.
    return []


def get_live_hotel_availability(
    *,
    hotel_name: str,
    city: str,
    state_country: str | None = None,
    checkin_date: str | None = None,
    checkout_date: str | None = None,
) -> tuple[str, int | None]:
    provider = current_app.config.get("HOTEL_PROVIDER", "rapidapi")
    gemini_api_key = current_app.config.get("GOOGLE_GEMINI_AI_API_KEY")
    places_api_key = current_app.config.get("GOOGLE_PLACES_API_KEY")
    gemini_model = current_app.config.get("GEMINI_MODEL", "gemini-flash-latest")
    rapidapi_key = current_app.config.get("RAPIDAPI_KEY")
    rapidapi_host = current_app.config.get("RAPIDAPI_HOST", "booking-com.p.rapidapi.com")
    rapidapi_locale = current_app.config.get("RAPIDAPI_LOCALE", "en-us")
    rapidapi_currency = current_app.config.get("RAPIDAPI_CURRENCY", "INR")
    rapidapi_timeout = int(current_app.config.get("RAPIDAPI_TIMEOUT_SECONDS", 15) or 15)

    rows = fetch_live_hotels(
        city,
        state_country=state_country,
        api_key=gemini_api_key,
        places_api_key=places_api_key,
        model=gemini_model,
        limit=15,
        provider=provider,
        rapidapi_key=rapidapi_key,
        rapidapi_host=rapidapi_host,
        rapidapi_locale=rapidapi_locale,
        rapidapi_currency=rapidapi_currency,
        rapidapi_timeout=rapidapi_timeout,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
    )
    target = (hotel_name or "").strip().lower()
    for row in rows:
        if str(row.get("name", "")).strip().lower() == target:
            return str(row.get("availability_status", "Live status unavailable")), row.get("rooms_available")
    return "Live status unavailable", None
