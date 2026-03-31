from __future__ import annotations

import json
import math
from datetime import date, timedelta
from urllib.parse import quote_plus
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from app.services.cache_service import api_cache
from app.services.gemini_service import gemini_generate_json


DEFAULT_DESTINATION_IMAGES = {
    "mumbai": "https://images.unsplash.com/photo-1526481280695-3c4691f241ac?auto=format&fit=crop&w=1200&q=80",
    "delhi": "https://images.unsplash.com/photo-1587474260584-136574528ed5?auto=format&fit=crop&w=1200&q=80",
    "goa": "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=1200&q=80",
    "jaipur": "https://images.unsplash.com/photo-1599661046827-dacde6976544?auto=format&fit=crop&w=1200&q=80",
    "manali": "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=1200&q=80",
    "bangalore": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "bengaluru": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "hyderabad": "https://images.unsplash.com/photo-1605333396915-47ed6b68a00e?auto=format&fit=crop&w=1200&q=80",
    "chennai": "https://images.unsplash.com/photo-1582510003544-4d00b7f74220?auto=format&fit=crop&w=1200&q=80",
    "kolkata": "https://images.unsplash.com/photo-1558434088-918448995a1b?auto=format&fit=crop&w=1200&q=80",
    "pune": "https://images.unsplash.com/photo-1543831306-25838031da29?auto=format&fit=crop&w=1200&q=80",
    "ahmedabad": "https://images.unsplash.com/photo-1634563811652-32a2656360c7?auto=format&fit=crop&w=1200&q=80",
    "surat": "https://images.unsplash.com/photo-1634563811652-32a2656360c7?auto=format&fit=crop&w=1200&q=80",
    "lucknow": "https://images.unsplash.com/photo-1563840746-996489370041?auto=format&fit=crop&w=1200&q=80",
    "amritsar": "https://images.unsplash.com/photo-1623594132030-cf2ba270a68d?auto=format&fit=crop&w=1200&q=80",
    "varanasi": "https://images.unsplash.com/photo-1561361513-2d000a501012?auto=format&fit=crop&w=1200&q=80",
    "agra": "https://images.unsplash.com/photo-1564507592333-c60657451dd6?auto=format&fit=crop&w=1200&q=80",
    "rishikesh": "https://images.unsplash.com/photo-1533604117777-62463e264264?auto=format&fit=crop&w=1200&q=80",
    "haridwar": "https://images.unsplash.com/photo-1533604117777-62463e264264?auto=format&fit=crop&w=1200&q=80",
    "shimla": "https://images.unsplash.com/photo-1624504192663-8a39e83ec50f?auto=format&fit=crop&w=1200&q=80",
    "dharamshala": "https://images.unsplash.com/photo-1583279177196-8ac54191ae0b?auto=format&fit=crop&w=1200&q=80",
    "leh": "https://images.unsplash.com/photo-1581793745862-99fde7fa73d2?auto=format&fit=crop&w=1200&q=80",
    "ladakh": "https://images.unsplash.com/photo-1581793745862-99fde7fa73d2?auto=format&fit=crop&w=1200&q=80",
    "srinagar": "https://images.unsplash.com/photo-1566833925222-38617f7d0bd7?auto=format&fit=crop&w=1200&q=80",
    "jammu": "https://images.unsplash.com/photo-1566833925222-38617f7d0bd7?auto=format&fit=crop&w=1200&q=80",
    "udaipur": "https://images.unsplash.com/photo-1639352220147-38f36cb077d8?auto=format&fit=crop&w=1200&q=80",
    "jodhpur": "https://images.unsplash.com/photo-1639352220147-38f36cb077d8?auto=format&fit=crop&w=1200&q=80",
    "pushkar": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "kochi": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "munnar": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "alleppey": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "thiruvananthapuram": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "mysore": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "coorg": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "ooty": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "madurai": "https://images.unsplash.com/photo-1596422846543-b5c64881fe53?auto=format&fit=crop&w=1200&q=80",
    "vishakhapatnam": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "vizag": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "bhubaneswar": "https://images.unsplash.com/photo-1558434088-918448995a1b?auto=format&fit=crop&w=1200&q=80",
    "puri": "https://images.unsplash.com/photo-1558434088-918448995a1b?auto=format&fit=crop&w=1200&q=80",
    "gangtok": "https://images.unsplash.com/photo-1558434088-918448995a1b?auto=format&fit=crop&w=1200&q=80",
    "darjeeling": "https://images.unsplash.com/photo-1558434088-918448995a1b?auto=format&fit=crop&w=1200&q=80",
    "andaman": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
    "port blair": "https://images.unsplash.com/photo-1561360064-96696dbd4c9d?auto=format&fit=crop&w=1200&q=80",
}

PREFERENCE_QUERY_TERMS = {
    "adventure": "adventure activities",
    "nightlife": "nightlife hotspots",
    "nature": "nature attractions",
    "cultural": "historical landmarks",
    "shopping": "shopping market",
    "relaxation": "relaxing places",
    "food": "best local restaurants",
}

OSM_PREFERENCE_QUERY_TERMS = {
    "adventure": "adventure activities",
    "nightlife": "nightlife",
    "nature": "nature park",
    "cultural": "tourist attractions",
    "shopping": "market",
    "relaxation": "scenic spots",
    "food": "restaurants",
}

NON_ATTRACTION_TERMS = {
    "assembly constituency",
    "constituency",
    "district",
    "ward",
    "division",
    "corporation",
    "state bank",
    "post office",
    "police station",
    "municipal",
}

INDIAN_STATES_AND_UT = {
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "andaman and nicobar",
    "chandigarh",
    "dadra and nagar haveli",
    "daman and diu",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
}

TYPE_TO_CATEGORY = {
    "tourist_attraction": "cultural",
    "museum": "cultural",
    "art_gallery": "cultural",
    "night_club": "nightlife",
    "bar": "nightlife",
    "amusement_park": "adventure",
    "aquarium": "adventure",
    "park": "nature",
    "natural_feature": "nature",
    "shopping_mall": "shopping",
    "department_store": "shopping",
    "market": "shopping",
    "restaurant": "food",
    "cafe": "food",
}

PRICE_LEVEL_TO_TICKET = {
    0: 0,
    1: 10,
    2: 25,
    3: 50,
    4: 80,
}

HOTEL_PRICE_LEVEL_BASE = {
    0: 1200,
    1: 2200,
    2: 4200,
    3: 7500,
    4: 12000,
}


def _fetch_json(url: str, headers: dict | None = None, timeout: int = 8):
    request = Request(
        url,
        headers=headers
        or {
            "User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_query(destination: str, state_country: str | None = None) -> str:
    parts = [destination.strip()]
    # Only keep country-like context. Ignore arbitrary state text if it can mislead geocoding.
    state_value = (state_country or "").strip().lower()
    country_context = None
    for country in [
        "india",
        "united states",
        "usa",
        "uk",
        "united kingdom",
        "france",
        "japan",
        "australia",
        "canada",
        "germany",
        "italy",
        "spain",
        "uae",
        "singapore",
        "thailand",
        "indonesia",
    ]:
        if country in state_value:
            country_context = country.title() if country != "usa" else "USA"
            break
    if country_context:
        parts.append(country_context)
    elif state_value in INDIAN_STATES_AND_UT:
        parts.append("India")
    return ", ".join([part for part in parts if part])


def _contains_destination(text: str, destination: str) -> bool:
    return destination.strip().lower() in (text or "").lower()


def _looks_like_attraction(text: str) -> bool:
    lower_text = (text or "").lower()
    return not any(term in lower_text for term in NON_ATTRACTION_TERMS)


def _is_within_radius_km(
    center_coords: tuple[float, float] | None,
    point_lat: float | None,
    point_lon: float | None,
    radius_km: float = 120.0,
) -> bool:
    if not center_coords:
        return True
    if point_lat is None or point_lon is None:
        return True
    try:
        distance = _distance_km(center_coords[0], center_coords[1], float(point_lat), float(point_lon))
        return distance <= radius_km
    except (TypeError, ValueError):
        return True


def build_maps_link(query: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def build_latlng_maps_link(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def build_place_id_maps_link(place_id: str, fallback_query: str) -> str:
    if place_id:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(fallback_query)}&query_place_id={quote_plus(place_id)}"
    return build_maps_link(fallback_query)


def destination_image_url(
    destination: str,
    state_country: str | None = None,
    google_places_api_key: str | None = None,
) -> str:
    normalized = destination.strip().lower()
    if normalized in DEFAULT_DESTINATION_IMAGES:
        return DEFAULT_DESTINATION_IMAGES[normalized]

    query = _build_query(destination, state_country)
    if google_places_api_key:
        return (
            "https://maps.googleapis.com/maps/api/streetview"
            f"?size=1200x700&location={quote_plus(query)}&key={quote_plus(google_places_api_key)}"
        )

    return f"https://loremflickr.com/1200/700/{quote_plus(query + ' travel destination')}"


def build_destination_cards(
    destinations: list[str],
    state_country: str | None = None,
    google_places_api_key: str | None = None,
) -> list[dict]:
    cards = []
    for destination in destinations:
        query = _build_query(destination, state_country)
        cards.append(
            {
                "name": destination,
                "image_url": destination_image_url(destination, state_country, google_places_api_key),
                "map_link": build_maps_link(query),
                "search_query": query,
            }
        )
    return cards


def _infer_category(place_types: list[str]) -> str:
    for item_type in place_types:
        if item_type in TYPE_TO_CATEGORY:
            return TYPE_TO_CATEGORY[item_type]
    return "cultural"


def _build_photo_url(photo_reference: str, api_key: str) -> str:
    params = urlencode(
        {
            "maxwidth": 1000,
            "photo_reference": photo_reference,
            "key": api_key,
        }
    )
    return f"https://maps.googleapis.com/maps/api/place/photo?{params}"


def _text_search(query: str, api_key: str) -> list[dict]:
    params = urlencode(
        {
            "query": query,
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?{params}"
    data = _fetch_json(url)
    return data.get("results") or []


def _text_search_payload(query: str, api_key: str) -> dict:
    params = urlencode(
        {
            "query": query,
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?{params}"
    data = _fetch_json(url)
    return data if isinstance(data, dict) else {}


@api_cache.memoize(key_prefix="osm_search", expiry_seconds=604800)
def _osm_search(query: str, limit: int = 15) -> list[dict]:
    params = urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
        }
    )
    data = _fetch_json(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
    )
    if isinstance(data, list):
        return data
    return []


@api_cache.memoize(key_prefix="openmeteo_coords", expiry_seconds=604800)
def _openmeteo_coords(query: str) -> tuple[float, float] | None:
    params = urlencode({"name": query, "count": 1, "language": "en", "format": "json"})
    data = _fetch_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    if not isinstance(data, dict):
        return None
    results = data.get("results") or []
    if not results:
        return None
    first = results[0]
    lat = first.get("latitude")
    lon = first.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _wikipedia_geosearch(lat: float, lon: float, limit: int = 25) -> list[dict]:
    params = urlencode(
        {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": 10000,
            "gslimit": min(limit, 50),
            "format": "json",
        }
    )
    data = _fetch_json(
        f"https://en.wikipedia.org/w/api.php?{params}",
        headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
    )
    if not isinstance(data, dict):
        return []
    return data.get("query", {}).get("geosearch", []) or []


def _resolve_destination_coords(destination: str, destination_query: str) -> tuple[float, float] | None:
    for query in [destination, destination_query]:
        rows = _osm_search(query, limit=1)
        if rows:
            try:
                return float(rows[0]["lat"]), float(rows[0]["lon"])
            except (KeyError, TypeError, ValueError):
                continue

    return _openmeteo_coords(destination) or _openmeteo_coords(destination_query)


@api_cache.memoize(key_prefix="google_geocode", expiry_seconds=604800)
def _geocode_query(query: str, api_key: str) -> tuple[float, float] | None:
    params = urlencode({"address": query, "key": api_key})
    data = _fetch_json(f"https://maps.googleapis.com/maps/api/geocode/json?{params}")
    results = data.get("results") or []
    if not results:
        return None
    location = results[0].get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def _build_osm_activity_rows(
    destination: str,
    destination_query: str,
    preferences: list[str],
    seen_names: set[str],
    limit: int,
) -> list[dict]:
    activities = []
    for pref in preferences:
        term = OSM_PREFERENCE_QUERY_TERMS.get(pref, "tourist attractions")
        query = f"{term} in {destination_query}"
        for row in _osm_search(query, limit=min(18, limit)):
            display_name = (row.get("display_name") or "").strip()
            if not display_name:
                continue
            if not _contains_destination(display_name, destination):
                continue
            if not _looks_like_attraction(display_name):
                continue
            name = (display_name.split(",")[0] or "").strip() or f"{destination} Spot"
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)

            try:
                lat = float(row.get("lat"))
                lon = float(row.get("lon"))
            except (TypeError, ValueError):
                continue

            category = pref
            rating = 4.0
            ticket = estimate_activity_price(None, rating, category)
            activities.append(
                {
                    "title": name,
                    "description": display_name,
                    "ticket": ticket,
                    "category": category,
                    "rating": rating,
                    "map_link": build_latlng_maps_link(lat, lon),
                    "image_url": None,
                    "lat": lat,
                    "lng": lon,
                }
            )
            if len(activities) >= limit:
                return activities
    return activities


def _build_wiki_activity_rows(
    destination: str,
    destination_query: str,
    preferences: list[str],
    seen_names: set[str],
    limit: int,
) -> list[dict]:
    coords = _resolve_destination_coords(destination.strip(), destination_query)
    if not coords:
        return []

    rows = _wikipedia_geosearch(coords[0], coords[1], limit=max(25, limit * 3))
    if not rows:
        return []

    categories = preferences if preferences else ["cultural", "nature", "food"]
    activities = []
    for idx, row in enumerate(rows):
        name = (row.get("title") or "").strip()
        if not name:
            continue
        if not _looks_like_attraction(name):
            continue
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue

        category = categories[idx % len(categories)]
        rating = 4.0
        ticket = estimate_activity_price(None, rating, category)
        activities.append(
            {
                "title": name,
                "description": f"Popular nearby place in {destination_query}.",
                "ticket": ticket,
                "category": category,
                "rating": rating,
                "map_link": build_latlng_maps_link(float(lat), float(lon)),
                "image_url": None,
                "lat": float(lat),
                "lng": float(lon),
            }
        )
        if len(activities) >= limit:
            return activities
    return activities


def _build_google_places_activity_rows(
    destination: str,
    destination_query: str,
    preferences: list[str],
    places_api_key: str,
    seen_names: set[str],
    limit: int,
) -> list[dict]:
    city_coords = _geocode_query(destination_query, places_api_key) or _resolve_destination_coords(destination, destination_query)
    query_plan = [(pref, PREFERENCE_QUERY_TERMS.get(pref, "top tourist attractions")) for pref in preferences]
    query_plan.append(("cultural", "top tourist attractions"))
    rows_out = []

    for preferred_category, term in query_plan:
        payload = _text_search_payload(f"{term} in {destination_query}", places_api_key)
        for result in payload.get("results") or []:
            name = str(result.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            if key in seen_names:
                continue

            address = str(result.get("formatted_address", "")).strip()
            if not _contains_destination(f"{name} {address}", destination):
                continue

            geometry = result.get("geometry", {}).get("location", {})
            lat = geometry.get("lat")
            lng = geometry.get("lng")
            if not _is_within_radius_km(city_coords, lat, lng, radius_km=120.0):
                continue

            place_types = result.get("types") or []
            category = _infer_category(place_types)
            if category == "cultural" and preferred_category in PREFERENCE_QUERY_TERMS:
                category = preferred_category

            rating = _to_float(result.get("rating", 4.0), 4.0)
            rating = max(3.5, min(5.0, rating))
            ticket = estimate_activity_price(result.get("price_level"), rating, category)
            place_id = str(result.get("place_id", "")).strip()
            map_link = build_place_id_maps_link(place_id, f"{name}, {address or destination_query}")

            image_url = None
            photos = result.get("photos") or []
            if photos and photos[0].get("photo_reference"):
                image_url = _build_photo_url(photos[0]["photo_reference"], places_api_key)
            if not image_url:
                image_url = f"https://source.unsplash.com/1200x700/?{quote_plus(name + ', ' + destination_query)}"

            seen_names.add(key)
            rows_out.append(
                {
                    "title": name,
                    "description": address or f"Popular place in {destination_query}.",
                    "ticket": round(ticket, 2),
                    "category": category,
                    "rating": round(rating, 1),
                    "map_link": map_link,
                    "image_url": image_url,
                    "lat": float(lat) if lat is not None else None,
                    "lng": float(lng) if lng is not None else None,
                }
            )
            if len(rows_out) >= limit:
                return rows_out
    return rows_out


@api_cache.memoize(key_prefix="destination_activities", expiry_seconds=43200)
def fetch_live_destination_activities(
    destination: str,
    state_country: str | None = None,
    preferences: list[str] | None = None,
    places_api_key: str | None = None,
    gemini_api_key: str | None = None,
    limit: int = 18,
    model: str = "gemini-flash-latest",
) -> list[dict]:
    normalized_prefs = [(p or "").strip().lower() for p in (preferences or []) if (p or "").strip()]
    if not normalized_prefs:
        normalized_prefs = ["cultural", "nature", "food"]

    destination_query = _build_query(destination, state_country)
    seen_names = set()

    # Primary source: Google Places (real place ids + accurate map links)
    if places_api_key:
        gp_rows = _build_google_places_activity_rows(
            destination=destination,
            destination_query=destination_query,
            preferences=normalized_prefs,
            places_api_key=places_api_key,
            seen_names=seen_names,
            limit=limit,
        )
        if gp_rows:
            return gp_rows

    # Fallback 1: Wikipedia geosearch (real geographic data)
    wiki_rows = _build_wiki_activity_rows(
        destination=destination,
        destination_query=destination_query,
        preferences=normalized_prefs,
        seen_names=seen_names,
        limit=limit,
    )
    if wiki_rows:
        return wiki_rows

    # Fallback 2: OpenStreetMap query (real map data)
    osm_rows = _build_osm_activity_rows(
        destination=destination,
        destination_query=destination_query,
        preferences=normalized_prefs,
        seen_names=seen_names,
        limit=limit,
    )
    if osm_rows:
        return osm_rows

    # Final optional fallback: Gemini-generated suggestions only if explicitly available.
    if gemini_api_key:
        prompt = (
            "Return only JSON array, no markdown.\n"
            f"Generate exactly {limit} real attractions for {destination_query}.\n"
            "Each item keys: title, address, description, category, rating, ticket_estimate_inr.\n"
            "Use only places that actually exist in that destination."
        )
        raw = gemini_generate_json(
            prompt=prompt,
            api_key=gemini_api_key,
            model=model,
            temperature=0.1,
            attempts=1,
            timeout_seconds=8,
        )
        if isinstance(raw, list):
            activities = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title", "")).strip()
                address = str(row.get("address", "")).strip()
                if not title or not _contains_destination(f"{title} {address}", destination):
                    continue
                key = title.lower()
                if key in seen_names:
                    continue
                seen_names.add(key)
                category = str(row.get("category", "cultural")).strip().lower()
                if category not in {"adventure", "nightlife", "nature", "cultural", "shopping", "relaxation", "food"}:
                    category = "cultural"
                rating = max(3.5, min(5.0, _to_float(row.get("rating", 4.0), 4.0)))
                ticket = max(0.0, _to_float(row.get("ticket_estimate_inr", estimate_activity_price(None, rating, category))))
                activities.append(
                    {
                        "title": title,
                        "description": str(row.get("description", "")).strip() or address or f"Popular place in {destination_query}.",
                        "ticket": round(ticket, 2),
                        "category": category,
                        "rating": round(rating, 1),
                        "map_link": build_maps_link(f"{title}, {address or destination_query}"),
                        "image_url": f"https://source.unsplash.com/1200x700/?{quote_plus(title + ', ' + destination_query)}",
                        "lat": None,
                        "lng": None,
                    }
                )
                if len(activities) >= limit:
                    return activities

    return []


def estimate_activity_price(price_level: int | None, rating: float, category: str) -> float:
    # Approximate ticket/activity cost dynamically from place cost signals.
    category_base = {
        "adventure": 45,
        "nightlife": 35,
        "nature": 20,
        "cultural": 25,
        "shopping": 15,
        "relaxation": 15,
        "food": 30,
    }
    price_component = PRICE_LEVEL_TO_TICKET.get(price_level, 15)
    rating_component = max(0.0, rating - 3.5) * 8
    base = category_base.get(category, 20)
    return round(base + price_component + rating_component, 2)


def estimate_hotel_price_range(price_level: int | None, rating: float) -> tuple[float, float]:
    nightly_base = HOTEL_PRICE_LEVEL_BASE.get(price_level, 4200)
    rating_bump = max(0.0, rating - 3.5) * 900
    price_min = max(1000.0, nightly_base + rating_bump)
    price_max = max(price_min + 1200.0, price_min * 1.7)
    return round(price_min, 2), round(price_max, 2)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _rapidapi_get_json(url: str, api_key: str, host: str, timeout: int = 15):
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": host,
        "User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)",
    }
    return _fetch_json(url, headers=headers, timeout=timeout)


def _resolve_rapidapi_destination(
    destination_query: str,
    rapidapi_key: str,
    rapidapi_host: str,
    rapidapi_locale: str,
    rapidapi_timeout: int = 15,
):
    def _best_match(rows: list[dict]) -> dict | None:
        if not rows:
            return None
        destination_name = (destination_query.split(",")[0] or "").strip().lower()
        country_hint = "india" if "india" in destination_query.lower() else ""
        best_row = None
        best_score = -1
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = json.dumps(row, ensure_ascii=False).lower()
            score = 0
            if destination_name and destination_name in text:
                score += 2
            if country_hint and country_hint in text:
                score += 1
            if score > best_score:
                best_score = score
                best_row = row
        return best_row or rows[0]

    # Provider A: booking-com.p.rapidapi.com
    if "booking-com.p.rapidapi.com" in rapidapi_host:
        params = urlencode({"name": destination_query, "locale": rapidapi_locale})
        payload = _rapidapi_get_json(
            f"https://{rapidapi_host}/v1/hotels/locations?{params}",
            api_key=rapidapi_key,
            host=rapidapi_host,
            timeout=rapidapi_timeout,
        )
        rows = payload if isinstance(payload, list) else []
        row = _best_match(rows)
        if isinstance(row, dict):
            dest_id = str(row.get("dest_id", "")).strip()
            dest_type = str(row.get("dest_type", "city")).strip() or "city"
            if dest_id:
                return dest_id, dest_type
        return None, None

    # Provider B: booking-com15.p.rapidapi.com
    if "booking-com15.p.rapidapi.com" in rapidapi_host:
        params = urlencode({"query": destination_query})
        payload = _rapidapi_get_json(
            f"https://{rapidapi_host}/api/v1/hotels/searchDestination?{params}",
            api_key=rapidapi_key,
            host=rapidapi_host,
            timeout=rapidapi_timeout,
        )
        rows = payload.get("data") if isinstance(payload, dict) else []
        rows = rows if isinstance(rows, list) else []
        row = _best_match(rows)
        if isinstance(row, dict):
            dest_id = str(row.get("dest_id", "")).strip()
            dest_type = str(row.get("dest_type", "city")).strip() or "city"
            if dest_id:
                return dest_id, dest_type
        return None, None

    return None, None


def _fetch_rapidapi_hotels(
    destination: str,
    destination_query: str,
    rapidapi_key: str,
    rapidapi_host: str,
    rapidapi_locale: str,
    rapidapi_currency: str,
    rapidapi_timeout: int,
    limit: int,
    checkin_date: str | None = None,
    checkout_date: str | None = None,
) -> list[dict]:
    dest_id, dest_type = _resolve_rapidapi_destination(
        destination_query=destination_query,
        rapidapi_key=rapidapi_key,
        rapidapi_host=rapidapi_host,
        rapidapi_locale=rapidapi_locale,
        rapidapi_timeout=rapidapi_timeout,
    )
    if not dest_id:
        return []

    checkin = (checkin_date or "").strip() or (date.today() + timedelta(days=14)).isoformat()
    checkout = (checkout_date or "").strip() or (date.today() + timedelta(days=16)).isoformat()

    def _availability_from_row(payload_row: dict) -> tuple[str, int | None]:
        raw_rooms = (
            payload_row.get("available_rooms")
            or payload_row.get("room_count")
            or payload_row.get("rooms_available")
            or payload_row.get("availableRooms")
            or payload_row.get("property", {}).get("availableRooms")
        )
        try:
            rooms = int(raw_rooms) if raw_rooms is not None else None
        except (TypeError, ValueError):
            rooms = None

        if rooms is not None:
            if rooms <= 0:
                return "Sold Out", 0
            if rooms <= 2:
                return "Limited", rooms
            return "Available", rooms

        raw_available = payload_row.get("is_available")
        if raw_available is None:
            raw_available = payload_row.get("available")
        if raw_available is None:
            sold_out = payload_row.get("sold_out")
            if sold_out is not None:
                raw_available = not bool(sold_out)

        if raw_available is True:
            return "Available", None
        if raw_available is False:
            return "Sold Out", None
        return "Live status unavailable", None

    payload = None
    if "booking-com.p.rapidapi.com" in rapidapi_host:
        params = urlencode(
            {
                "checkin_date": checkin,
                "checkout_date": checkout,
                "units": "metric",
                "adults_number": 1,
                "room_number": 1,
                "dest_id": dest_id,
                "dest_type": dest_type or "city",
                "order_by": "popularity",
                "locale": rapidapi_locale,
                "filter_by_currency": rapidapi_currency,
                "page_number": 0,
            }
        )
        payload = _rapidapi_get_json(
            f"https://{rapidapi_host}/v1/hotels/search?{params}",
            api_key=rapidapi_key,
            host=rapidapi_host,
            timeout=rapidapi_timeout,
        )
        rows = payload.get("result") if isinstance(payload, dict) else []
    elif "booking-com15.p.rapidapi.com" in rapidapi_host:
        params = urlencode(
            {
                "dest_id": dest_id,
                "search_type": (dest_type or "CITY").upper(),
                "arrival_date": checkin,
                "departure_date": checkout,
                "adults": 1,
                "children_age": "0,17",
                "room_qty": 1,
                "page_number": 1,
                "units": "metric",
                "temperature_unit": "c",
                "languagecode": rapidapi_locale,
                "currency_code": rapidapi_currency,
            }
        )
        payload = _rapidapi_get_json(
            f"https://{rapidapi_host}/api/v1/hotels/searchHotels?{params}",
            api_key=rapidapi_key,
            host=rapidapi_host,
            timeout=rapidapi_timeout,
        )
        data = payload.get("data") if isinstance(payload, dict) else {}
        rows = data.get("hotels") if isinstance(data, dict) else []
    else:
        rows = []

    rows = rows if isinstance(rows, list) else []
    hotels = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue

        name = (
            row.get("hotel_name")
            or row.get("name")
            or row.get("property", {}).get("name")
            or row.get("hotelName")
            or ""
        )
        name = str(name).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        address = (
            row.get("address")
            or row.get("address_trans")
            or row.get("accessibilityLabel")
            or row.get("wishlistName")
            or destination_query
        )
        address = str(address).strip() or destination_query

        rating = (
            row.get("review_score")
            or row.get("reviewScore")
            or row.get("property", {}).get("reviewScore")
            or row.get("star_rating")
            or 4.0
        )
        rating = max(3.5, min(5.0, _to_float(rating, 4.0)))

        raw_price = (
            row.get("min_total_price")
            or row.get("min_total_price_per_night")
            or row.get("priceBreakdown", {}).get("grossPrice", {}).get("value")
            or row.get("compositePriceBreakdown", {}).get("grossAmount", {}).get("value")
            or row.get("price")
            or 0
        )
        price_min = _to_float(raw_price, 0.0)
        price_max = price_min
        if price_min <= 0:
            est_min, est_max = estimate_hotel_price_range(None, rating)
            price_min, price_max = est_min, est_max
        else:
            price_max = max(price_min + 750, round(price_min * 1.25, 2))

        distance = row.get("distance_to_cc") or row.get("distance") or row.get("distanceToCc") or 2.5
        distance_km = max(0.1, _to_float(distance, 2.5))
        availability_status, rooms_available = _availability_from_row(row)

        hotels.append(
            {
                "name": name,
                "city": destination,
                "address": address,
                "price_min": round(price_min, 2),
                "price_max": round(price_max, 2),
                "rating": round(rating, 1),
                "distance_km": round(distance_km, 2),
                "map_link": build_maps_link(f"{name}, {address}"),
                "availability_status": availability_status,
                "rooms_available": rooms_available,
            }
        )
        if len(hotels) >= limit:
            break

    return hotels


def _fetch_google_places_hotels(
    destination: str,
    destination_query: str,
    places_api_key: str,
    limit: int,
) -> list[dict]:
    results = _text_search(f"best hotels in {destination_query}", places_api_key)
    city_coords = _geocode_query(destination_query, places_api_key) or _resolve_destination_coords(destination, destination_query)
    hotels = []
    seen = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        address = str(row.get("formatted_address", "")).strip() or destination_query
        geometry = row.get("geometry", {}).get("location", {})
        lat = geometry.get("lat")
        lng = geometry.get("lng")
        if city_coords and lat is not None and lng is not None:
            if not _is_within_radius_km(city_coords, lat, lng, radius_km=120.0):
                continue

        rating = _to_float(row.get("rating", 4.0), 4.0)
        rating = max(3.5, min(5.0, rating))
        price_level = row.get("price_level")
        price_min, price_max = estimate_hotel_price_range(price_level, rating)

        distance_km = 2.5
        if city_coords and lat is not None and lng is not None:
            distance_km = _distance_km(city_coords[0], city_coords[1], float(lat), float(lng))

        place_id = str(row.get("place_id", "")).strip()
        map_link = build_place_id_maps_link(place_id, f"{name}, {address}")
        hotels.append(
            {
                "name": name,
                "city": destination,
                "address": address,
                "price_min": round(price_min, 2),
                "price_max": round(price_max, 2),
                "rating": round(rating, 1),
                "distance_km": round(max(0.1, distance_km), 2),
                "map_link": map_link,
            }
        )
        if len(hotels) >= limit:
            break
    return hotels


@api_cache.memoize(key_prefix="live_hotels", expiry_seconds=86400)
def fetch_live_hotels(
    city: str,
    state_country: str | None = None,
    api_key: str | None = None,
    places_api_key: str | None = None,
    model: str = "gemini-flash-latest",
    limit: int = 15,
    provider: str = "rapidapi",
    rapidapi_key: str | None = None,
    rapidapi_host: str | None = None,
    rapidapi_locale: str | None = None,
    rapidapi_currency: str | None = "INR",
    rapidapi_timeout: int = 15,
    checkin_date: str | None = None,
    checkout_date: str | None = None,
) -> list[dict]:
    destination_query = _build_query(city, state_country)
    hotels: list[dict] = []
    seen_names: set[str] = set()

    def _append_hotel(row: dict):
        if not isinstance(row, dict):
            return
        name = str(row.get("name", "")).strip()
        if not name:
            return
        key = name.lower()
        if key in seen_names:
            return
        seen_names.add(key)

        address = str(row.get("address", "")).strip() or destination_query
        rating = max(3.5, min(5.0, _to_float(row.get("rating", 4.0), 4.0)))
        price_min = _to_float(row.get("price_min", 0), 0.0)
        price_max = _to_float(row.get("price_max", 0), 0.0)
        if price_min <= 0 or price_max <= 0:
            est_min, est_max = estimate_hotel_price_range(None, rating)
            price_min, price_max = est_min, est_max
        if price_max < price_min:
            price_max = price_min
        distance_km = max(0.1, _to_float(row.get("distance_km", 2.5), 2.5))
        map_link = str(row.get("map_link", "")).strip() or build_maps_link(f"{name}, {address}")

        hotels.append(
            {
                "name": name,
                "city": city,
                "address": address,
                "price_min": round(price_min, 2),
                "price_max": round(price_max, 2),
                "rating": round(rating, 1),
                "distance_km": round(distance_km, 2),
                "map_link": map_link,
                "availability_status": str(row.get("availability_status", "Live status unavailable")),
                "rooms_available": row.get("rooms_available"),
            }
        )

    if provider == "rapidapi" and rapidapi_key:
        try:
            rapid_rows = _fetch_rapidapi_hotels(
                destination=city,
                destination_query=destination_query,
                rapidapi_key=rapidapi_key,
                rapidapi_host=rapidapi_host,
                rapidapi_locale=rapidapi_locale,
                rapidapi_currency=rapidapi_currency,
                rapidapi_timeout=rapidapi_timeout,
                limit=limit,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
            )
            for row in rapid_rows:
                _append_hotel(row)
            if len(hotels) >= limit:
                return hotels[:limit]
        except Exception:
            # Fallback to gemini provider below.
            pass

    if api_key and len(hotels) < limit:
        remaining = max(3, limit - len(hotels))
        prompt = (
            "You are a travel data API. Return only JSON array with no markdown.\n"
            f"Provide {remaining} high-quality hotel recommendations for the city of '{city}' in '{state_country}'.\n"
            "Each item must include keys: name, address, rating, price_min_inr, price_max_inr, distance_km.\n"
            "Rules: hotels must belong to destination city/region; rating between 3.5 and 5.0; "
            "price_max_inr >= price_min_inr; distance_km numeric."
        )
        raw = gemini_generate_json(
            prompt=prompt,
            api_key=api_key,
            model=model,
            temperature=0.2,
            attempts=1,
            timeout_seconds=10,
        )
        if isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name", "")).strip()
                if not name:
                    continue
                address = str(row.get("address", "")).strip() or destination_query
                rating = _to_float(row.get("rating", 4.0), 4.0)
                price_min = _to_float(row.get("price_min_inr", 0), 0.0)
                price_max = _to_float(row.get("price_max_inr", price_min), price_min)
                if price_min <= 0 or price_max <= 0:
                    est_min, est_max = estimate_hotel_price_range(None, rating)
                    price_min, price_max = est_min, est_max
                if price_max < price_min:
                    price_max = price_min
                distance_km = _to_float(row.get("distance_km", 2.5), 2.5)
                _append_hotel(
                    {
                        "name": name,
                        "address": address,
                        "price_min": price_min,
                        "price_max": price_max,
                        "rating": rating,
                        "distance_km": distance_km,
                        "map_link": build_maps_link(f"{name}, {address}"),
                    }
                )
                if len(hotels) >= limit:
                    return hotels[:limit]

    # Google Places fallback for real hotel entities.
    if places_api_key and len(hotels) < limit:
        try:
            gp_rows = _fetch_google_places_hotels(
                destination=city,
                destination_query=destination_query,
                places_api_key=places_api_key,
                limit=max(10, limit),
            )
            for row in gp_rows:
                _append_hotel(row)
                if len(hotels) >= limit:
                    return hotels[:limit]
        except Exception:
            pass

    # Final top-up: OSM hotel search with estimated pricing.
    if len(hotels) < limit:
        for row in _osm_search(f"hotels in {destination_query}", limit=max(20, limit * 4)):
            display_name = str(row.get("display_name", "")).strip()
            if not display_name:
                continue
            if not _contains_destination(display_name, city):
                continue
            name = (display_name.split(",")[0] or "").strip() or f"{city} Hotel"
            est_min, est_max = estimate_hotel_price_range(None, 4.1)
            _append_hotel(
                {
                    "name": name,
                    "address": display_name,
                    "price_min": est_min,
                    "price_max": est_max,
                    "rating": 4.1,
                    "distance_km": 2.5,
                    "map_link": build_maps_link(display_name),
                }
            )
            if len(hotels) >= limit:
                break

    if len(hotels) < limit:
        # Final deterministic fill so UI never gets too few hotel cards.
        for idx in range(limit - len(hotels)):
            rating = 4.1 + (idx % 3) * 0.1
            est_min, est_max = estimate_hotel_price_range(None, rating)
            name = f"{city} Stay {len(hotels) + 1}"
            _append_hotel(
                {
                    "name": name,
                    "address": destination_query,
                    "price_min": est_min,
                    "price_max": est_max,
                    "rating": rating,
                    "distance_km": 2.5 + (idx * 0.3),
                    "map_link": build_maps_link(f"{name}, {destination_query}"),
                }
            )

    return hotels[:limit]
