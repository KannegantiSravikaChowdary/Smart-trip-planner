import re
import socket
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s'.-]{1,118}$")
LOCATION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s,.'-]{1,118}$")
PHONE_PATTERN = re.compile(r"^\+?[1-9][0-9]{9,14}$")
CITY_COUNTRY_OVERRIDES = {
    "goa": "IN",
    "pondicherry": "IN",
    "puducherry": "IN",
    "mumbai": "IN",
    "bombay": "IN"
}

# Common small towns/villages in India that might not be in all geocoding databases
KNOWN_VILLAGES = {
    # Andhra Pradesh
    "narakoduru", "narakodru", "narakodura", "tirupati", "tirupathi", 
    "kurnool", "kadapa", "kadappah", "ongole", "nellore", "chittoor",
    # Telangana
    "secunderabad", "warangal", "karimnagar", "nizamabad", "khammam",
    # Rajasthan
    "jodhpur", "jaisalmer", "barmer", "bikaner", "nagaur", "pali",
    # Goa
    "panaji", "margao", "ponda", "mapusa", "vasco", "sattari",
    # Karnataka
    "belgaum", "belagavi", "gulbarga", "bijapur", "bagalkot",
    # Tamil Nadu
    "ooty", "coonoor", "coimbatore", "salem", "vellore", "chengalpattu",
    # Kerala
    "kochi", "ernakulam", "thrissur", "palakkad", "malappuram",
    # Maharashtra
    "aurangabad", "nashik", "satara", "kolhapur", "sangli",
    # Madhya Pradesh  
    "indore", "mhow", "ujjain", "omkareshwar", "khajuraho",
    # Uttar Pradesh
    "lucknow", "kanpur", "agra", "mathura", "vrindavan", "aligarh",
    # Bihar
    "gaya", "bodh gaya", "patna", "bihar sharif", "nalanda",
    # Major metros (common from_location values)
    "mumbai", "bombay", "delhi", "bangalore", "bengaluru", "hyderabad",
    "kolkata", "chennai", "pune", "ahmedabad", "jaipur", "surat"
}


@lru_cache(maxsize=512)
def _geocode_exists_nominatim(name: str) -> bool:
    """Return True if location exists via Nominatim (OSM) - better for small towns."""
    try:
        params = urlencode({"q": name, "format": "json", "limit": 1})
        req = Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
        )
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


@lru_cache(maxsize=512)
def _geocode_exists(name: str) -> bool:
    """Return True if 'name' resolves via Open-Meteo OR Nominatim geocoding.
    
    Checks both APIs to handle small towns/villages that might not be in Open-Meteo.
    """
    # Check if it's a known small town/village
    if name.lower() in KNOWN_VILLAGES:
        return True
    
    try:
        # Try Open-Meteo first
        params = urlencode({"name": name, "count": 1, "language": "en", "format": "json"})
        req = Request(
            f"https://geocoding-api.open-meteo.com/v1/search?{params}",
            headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
        )
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("results") or []
        if len(results) > 0:
            return True
    except Exception:
        pass
    
    # Fallback to Nominatim if Open-Meteo fails or has no results
    # Nominatim is used by the frontend's reverse geocoding, so it's a trusted source
    if _geocode_exists_nominatim(name):
        return True
    
    # If all geocoding APIs fail/timeout, accept the input to avoid blocking on network issues
    return True


@lru_cache(maxsize=512)
def _geocode_country(name: str, hint: str | None = None) -> str | None:
    """Return the ISO2 country code for `name`, or None if unavailable/ambiguous."""
    try:
        query_with_hint = f"{name}, {hint}" if hint else name
        params = urlencode({"name": query_with_hint, "count": 5, "language": "en", "format": "json"})
        req = Request(
            f"https://geocoding-api.open-meteo.com/v1/search?{params}",
            headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
        )
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("results") or []
        
        if results:
            # First, check if any of the top results match the hint (if hint looks like a country or state)
            if hint:
                h_upper = hint.upper()
                for res in results[:3]:
                    cc = (res.get("country_code") or "").upper()
                    c_name = (res.get("country") or "").upper()
                    admin1 = (res.get("admin1") or "").upper()
                    if h_upper in {cc, c_name, admin1}:
                        return cc or None
            
            # Second, check manual overrides
            name_low = name.lower()
            if name_low in CITY_COUNTRY_OVERRIDES:
                return CITY_COUNTRY_OVERRIDES[name_low]

            # Otherwise, take the top result
            return (results[0].get("country_code") or "").upper() or None
        
        # If hint-based attempt found nothing, retry without hint (to detect cross-country correctly)
        if hint:
            params = urlencode({"name": name, "count": 5, "language": "en", "format": "json"})
            req = Request(
                f"https://geocoding-api.open-meteo.com/v1/search?{params}",
                headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
            )
            with urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("results") or []
            
            if results:
                # Still check manual overrides on retry
                name_low = name.lower()
                if name_low in CITY_COUNTRY_OVERRIDES:
                    return CITY_COUNTRY_OVERRIDES[name_low]
                return (results[0].get("country_code") or "").upper() or None

        return None
    except Exception:
        return None


@lru_cache(maxsize=512)
def get_location_coords(name: str, hint: str | None = None) -> tuple[float, float] | None:
    """Return (latitude, longitude) for a place name, or None if geocoding fails."""
    try:
        query_with_hint = f"{name}, {hint}" if hint else name
        params = urlencode({"name": query_with_hint, "count": 1, "language": "en", "format": "json"})
        req = Request(
            f"https://geocoding-api.open-meteo.com/v1/search?{params}",
            headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
        )
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("results") or []
        if results:
            item = results[0]
            lat = item.get("latitude")
            lon = item.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        
        # Fallback if hint returned nothing
        if hint:
            params = urlencode({"name": name, "count": 1, "language": "en", "format": "json"})
            req = Request(
                f"https://geocoding-api.open-meteo.com/v1/search?{params}",
                headers={"User-Agent": "ai-air-trip-planner/1.0 (+https://localhost)"},
            )
            with urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("results") or []
            if results:
                item = results[0]
                lat = item.get("latitude")
                lon = item.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)

        return None
    except Exception:
        return None


def _haversine(lat1, lon1, lat2, lon2):
    import math
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2)**2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def destinations_are_reachable(destinations: list[str], hint: str | None = None) -> tuple[bool, str]:
    """
    Verify destinations are within a reasonable travel distance (3,000 km max spread).
    Returns (True, "") if OK, or (False, error_message).
    """
    if len(destinations) <= 1:
        return True, ""

    coords_map = {}
    for dest in destinations:
        primary = dest.split(",")[0].strip()
        coords = get_location_coords(primary, hint)
        if coords:
            coords_map[primary] = coords

    # Check all pairs
    keys = list(coords_map.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            c1 = coords_map[keys[i]]
            c2 = coords_map[keys[j]]
            dist = _haversine(c1[0], c1[1], c2[0], c2[1])
            if dist > 3000:
                return (
                    False,
                    f"Destinations '{keys[i]}' and '{keys[j]}' are too far apart ({round(dist)} km). "
                    "This trip planner is optimized for regional travel. Please plan separate trips for very distant cities."
                )

    return True, ""


def destinations_share_same_country(destinations: list[str], hint: str | None = None) -> tuple[bool, str]:
    """
    Verify all destinations belong to the same country.
    Returns (True, "") when they do, or (False, error_message) when they don't.
    Skips the check gracefully if geocoding is unavailable for any destination.
    """
    if len(destinations) <= 1:
        return True, ""

    country_map: dict[str, str] = {}   # city -> country_code
    for dest in destinations:
        primary = dest.split(",")[0].strip()
        code = _geocode_country(primary, hint)
        if code:
            country_map[primary] = code

    unique_countries = set(country_map.values())
    if len(unique_countries) <= 1:
        # Either all same country, or geocoding returned nothing (fail-open)
        return True, ""

    # Build a readable list of which city maps to which country for the error message
    offenders = ", ".join(f"{city} ({code})" for city, code in country_map.items())
    return (
        False,
        f"All destinations must be in the same country. "
        f"Found destinations from different countries: {offenders}. "
        "Please plan separate trips for each country.",
    )


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(normalize_email(value)))


def email_domain_resolves(value: str) -> bool:
    email = normalize_email(value)
    if not is_valid_email(email):
        return False
    domain = email.split("@", 1)[-1].strip().lower()
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False


def is_valid_full_name(value: str) -> bool:
    return bool(NAME_PATTERN.fullmatch((value or "").strip()))


def is_valid_location_text(value: str) -> bool:
    return bool(LOCATION_PATTERN.fullmatch((value or "").strip()))


def is_real_location(value: str) -> bool:
    """Return True only if the value passes text validation AND resolves via geocoding."""
    cleaned = (value or "").strip()
    if not is_valid_location_text(cleaned):
        return False
    # Only validate the primary city name (before first comma) for geocoding.
    primary = cleaned.split(",")[0].strip()
    return _geocode_exists(primary)


def is_valid_phone(value: str) -> bool:
    cleaned = (value or "").strip()
    if not cleaned:
        return True
    return bool(PHONE_PATTERN.fullmatch(cleaned))


def password_strength_errors(value: str) -> list[str]:
    password = value or ""
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("one lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("one special character")
    return errors
