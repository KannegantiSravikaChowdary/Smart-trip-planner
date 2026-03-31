from datetime import datetime

from app.services.validation_service import (
    destinations_are_reachable,
    destinations_share_same_country,
    is_real_location,
    is_valid_location_text,
)


def parse_trip_form(form):
    raw_destinations = form.get("destinations", "")
    dest_list = [item.strip() for item in raw_destinations.replace("\n", ",").split(",") if item.strip()]
    
    seen = set()
    destinations = []
    for d in dest_list:
        lower_d = d.lower()
        if lower_d not in seen:
            seen.add(lower_d)
            destinations.append(d)

    preferences = form.getlist("preferences")

    return {
        "from_location": form.get("from_location", "").strip(),
        "destinations": destinations,
        "state_country": form.get("state_country", "").strip(),
        "start_date": datetime.strptime(form.get("start_date"), "%Y-%m-%d").date(),
        "number_of_days": int(form.get("number_of_days", 1)),
        "number_of_people": int(form.get("number_of_people", 1)),
        "budget": float(form.get("budget", 0)),
        "travel_mode": form.get("travel_mode", "flight").lower(),
        "travel_type": form.get("travel_type", "solo").lower(),
        "preferences": preferences,
        "service_charge": float(form.get("service_charge", 0) or 0),
        "status": form.get("status", "draft").lower(),
        "places_per_day": int(form.get("places_per_day", 4) or 4),
    }


def validate_trip_payload(data):
    required = ["from_location", "state_country", "travel_mode", "travel_type"]
    for field in required:
        if not data.get(field):
            return False, f"{field.replace('_', ' ').title()} is required."

    if not data["destinations"]:
        return False, "At least one destination is required."
    if not is_valid_location_text(data["from_location"]):
        return False, "From Location must contain letters only (no numbers-only values)."
    if not is_real_location(data["from_location"]):
        return False, f"From Location '{data['from_location']}' does not appear to be a real place. Please enter a valid city or town."
    if not is_valid_location_text(data["state_country"]):
        return False, "State / Country must contain letters only (no numbers-only values)."
    for destination in data["destinations"]:
        if not is_valid_location_text(destination):
            return False, f"Destination '{destination}' is invalid. Use place names only."
        if not is_real_location(destination):
            return False, f"Destination '{destination}' does not appear to be a real place. Please enter a valid city or region."
    ok, country_error = destinations_share_same_country(data["destinations"], hint=data.get("state_country"))
    if not ok:
        return False, country_error
    
    ok, distance_error = destinations_are_reachable(data["destinations"], hint=data.get("state_country"))
    if not ok:
        return False, distance_error
    if data["number_of_days"] <= 0:
        return False, "Number of days must be greater than zero."
    if data["number_of_days"] < len(data["destinations"]):
        return False, "Number of days must be at least equal to destination count."
    if data["number_of_people"] <= 0:
        return False, "Number of people must be greater than zero."
    if data["places_per_day"] < 3 or data["places_per_day"] > 6:
        return False, "Places per day must be between 3 and 6."
    return True, ""
