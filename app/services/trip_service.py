import concurrent.futures
import math
import random
import time
from collections import defaultdict

from flask import current_app
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import Activity, Destination, Itinerary, Trip
from app.services.budget_service import calculate_budget
from app.services.hotel_service import recommended_hotels
from app.services.place_service import build_maps_link, fetch_live_destination_activities
from app.services.weather_service import get_live_weather

ALL_TIME_SLOTS = ["Early Morning", "Morning", "Afternoon", "Evening", "Night", "Late Night"]
MIN_SERVICE_CHARGE = 300.0
MIN_HOTEL_DAILY_PER_ROOM = 800.0
MIN_FOOD_DAILY_PER_PERSON = 250.0


def run_in_context(app, func, *args, **kwargs):
    with app.app_context():
        return func(*args, **kwargs)


def resolve_time_slots(places_per_day: int | None) -> list[str]:
    try:
        count = int(places_per_day or 4)
    except (TypeError, ValueError):
        count = 4
    count = max(3, min(6, count))
    return ALL_TIME_SLOTS[:count]


def infer_places_per_day(trip: Trip, fallback: int = 4) -> int:
    if not trip.itineraries:
        return max(3, min(6, int(fallback)))
    counts: dict[int, int] = defaultdict(int)
    for item in trip.itineraries:
        counts[item.day_number] += 1
    if not counts:
        return max(3, min(6, int(fallback)))
    return max(3, min(6, max(counts.values())))


def _time_slot_rank(value: str) -> int:
    normalized = (value or "").strip().lower()
    for idx, slot in enumerate(ALL_TIME_SLOTS):
        if slot.lower() == normalized:
            return idx
    return 99


def _is_sqlite_locked_error(exc: Exception) -> bool:
    return "database is locked" in str(exc).lower()


def _run_with_db_retry(action, attempts: int = 8, base_delay: float = 0.35):
    for attempt in range(attempts):
        try:
            return action()
        except OperationalError as exc:
            if _is_sqlite_locked_error(exc) and attempt < attempts - 1:
                db.session.rollback()
                time.sleep(base_delay * (attempt + 1))
                continue
            raise


def parse_destinations(raw_destinations: str) -> list[str]:
    values = [x.strip() for x in raw_destinations.replace("\n", ",").split(",")]
    return [value for value in values if value]


def distribute_days(total_days: int, destinations: list[str]) -> list[int]:
    if not destinations:
        return []

    base = total_days // len(destinations)
    remainder = total_days % len(destinations)
    return [base + (1 if idx < remainder else 0) for idx in range(len(destinations))]


def _title_key(item: dict) -> str:
    return str(item.get("title", "")).strip().lower()


def _item_coord(item: dict):
    lat = item.get("lat")
    lng = item.get("lng")
    try:
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _distance_km(coord1, coord2) -> float:
    if not coord1 or not coord2:
        return 25.0
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def _choose_day_choices(
    pool: list[dict],
    used_titles_global: set[str],
    slots: int,
    start_coord,
    rng: random.Random | None = None,
):
    def _pick_from(candidates: list[dict], current_coord, local_used: set[str]):
        available = [c for c in candidates if _title_key(c) and _title_key(c) not in local_used]
        if not available:
            return None
        ranked = sorted(
            available,
            key=lambda c: (
                _distance_km(current_coord, _item_coord(c)),
                -float(c.get("rating", 0) or 0),
            ),
        )
        if rng:
            return rng.choice(ranked[: min(4, len(ranked))])
        return ranked[0]

    fresh_pool = [p for p in pool if _title_key(p) and _title_key(p) not in used_titles_global]
    day_choices = []
    local_used: set[str] = set()
    current_coord = start_coord

    for source_pool in [fresh_pool, pool]:
        while len(day_choices) < slots:
            picked = _pick_from(source_pool, current_coord, local_used)
            if not picked:
                break
            day_choices.append(picked)
            local_used.add(_title_key(picked))
            coord = _item_coord(picked)
            if coord:
                current_coord = coord
        if len(day_choices) >= slots:
            break

    if len(day_choices) < slots:
        for item in pool:
            if len(day_choices) >= slots:
                break
            key = _title_key(item)
            if not key or key in local_used:
                continue
            day_choices.append(item)
            local_used.add(key)

    return day_choices


def _destination_activities(destination: str, state_country: str, preferences: list[str], minimum_items: int):
    places_api_key = current_app.config.get("GOOGLE_PLACES_API_KEY")
    gemini_api_key = current_app.config.get("GOOGLE_GEMINI_AI_API_KEY")
    gemini_model = current_app.config.get("GEMINI_MODEL", "gemini-flash-latest")
    try:
        live_pool = fetch_live_destination_activities(
            destination=destination,
            state_country=state_country,
            preferences=preferences,
            places_api_key=places_api_key,
            gemini_api_key=gemini_api_key,
            model=gemini_model,
            limit=minimum_items,
        )
    except Exception as exc:
        current_app.logger.warning("Activity provider failed for %s (%s).", destination, exc)
        live_pool = []

    return live_pool


def _build_itinerary_rows(
    trip: Trip,
    destinations: list[str],
    day_distribution: list[int],
    all_preferences: list[str],
    time_slots: list[str],
    regeneration_seed: int | None = None,
):
    day_counter = 1
    total_activity_cost = 0.0
    itinerary_rows = []
    rng = random.Random(regeneration_seed) if regeneration_seed is not None else None

    app = current_app._get_current_object()
    pools_by_dest = {}
    weather_by_day = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(destinations) * 2 + 1)) as executor:
        dest_futures = {}
        for idx, destination_name in enumerate(destinations):
            minimum_items = max(24, day_distribution[idx] * len(time_slots) + 6)
            dest_futures[destination_name] = executor.submit(
                run_in_context, app, _destination_activities, destination_name, trip.state_country, all_preferences, minimum_items
            )
        
        weather_futures = {}
        temp_day_counter = 1
        weather_provider = current_app.config.get("WEATHER_PROVIDER", "open-meteo")
        for idx, destination_name in enumerate(destinations):
            for _ in range(day_distribution[idx]):
                day_offset = temp_day_counter - 1
                weather_futures[(destination_name, day_offset)] = executor.submit(
                    run_in_context, app, get_live_weather, destination_name, trip.start_date, day_offset, weather_provider
                )
                temp_day_counter += 1

        for dest, future in dest_futures.items():
            pools_by_dest[dest] = future.result()

        for key, future in weather_futures.items():
            weather_by_day[key] = future.result()

    for idx, destination_name in enumerate(destinations):
        activity_pool = pools_by_dest[destination_name]
        if not activity_pool:
            raise RuntimeError(
                f"No real places found for '{destination_name}'. "
                "Check GOOGLE_PLACES_API_KEY and destination spelling."
            )

        unique_pool = []
        seen_titles = set()
        for item in activity_pool:
            title_key = _title_key(item)
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            unique_pool.append(item)
        if not unique_pool:
            raise RuntimeError(f"No unique places available for '{destination_name}'.")
        if rng and len(unique_pool) > 1:
            rng.shuffle(unique_pool)

        used_titles_global: set[str] = set()
        prev_day_last_coord = None
        for _ in range(day_distribution[idx]):
            start_coord = prev_day_last_coord
            if rng and start_coord is None and unique_pool:
                start_coord = _item_coord(rng.choice(unique_pool))
            day_choices = _choose_day_choices(
                pool=unique_pool,
                used_titles_global=used_titles_global,
                slots=len(time_slots),
                start_coord=start_coord,
                rng=rng,
            )
            if len(day_choices) < len(time_slots):
                raise RuntimeError(f"Not enough places available for day planning in '{destination_name}'.")

            for chosen in day_choices:
                key = _title_key(chosen)
                if key:
                    used_titles_global.add(key)
            prev_day_last_coord = _item_coord(day_choices[-1]) or prev_day_last_coord

            day_offset = day_counter - 1
            weather_info = weather_by_day.get((destination_name, day_offset))
            if not weather_info:
                weather_info = {"summary": "Weather update available."}

            for slot_idx, time_slot in enumerate(time_slots):
                choice = day_choices[slot_idx]
                map_link = choice.get("map_link")
                if not map_link:
                    map_query = f"{choice['title']}, {destination_name}, {trip.state_country}"
                    map_link = build_maps_link(map_query)

                ticket_price = float(choice.get("ticket", 0) or 0)
                itinerary_rows.append(
                    {
                        "destination_index": idx,
                        "destination_name": destination_name,
                        "day_number": day_counter,
                        "time_slot": time_slot,
                        "title": choice["title"],
                        "description": choice["description"],
                        "ticket_price": ticket_price,
                        "weather_summary": weather_info["summary"],
                        "map_link": map_link,
                        "rating": choice.get("rating", 4.0),
                        "category": choice.get("category", "cultural"),
                        "latitude": choice.get("lat"),
                        "longitude": choice.get("lng"),
                    }
                )
                total_activity_cost += ticket_price
            day_counter += 1

    return itinerary_rows, total_activity_cost


def _calculate_budget_for_rows(
    trip: Trip,
    destinations: list[str],
    average_hotel_rate: float,
    itinerary_rows: list[dict],
) -> dict:
    total_activity_cost = sum(float(row.get("ticket_price", 0) or 0) for row in itinerary_rows)
    return calculate_budget(
        primary_destination=destinations[0] if destinations else "Generic",
        number_of_days=trip.number_of_days,
        number_of_people=trip.number_of_people,
        travel_mode=trip.travel_mode,
        travel_type=trip.travel_type,
        hotel_rate=average_hotel_rate,
        activity_cost=total_activity_cost,
        destination_count=max(1, len(destinations)),
        service_charge=trip.service_charge,
        user_budget=trip.budget,
    )


def _prepare_plan_data(
    trip: Trip,
    regeneration_seed: int | None = None,
    places_per_day: int | None = None,
) -> dict:
    destinations = parse_destinations(trip.destinations_raw)
    day_distribution = distribute_days(trip.number_of_days, destinations)
    all_preferences = [p.lower() for p in trip.preferences]
    time_slots = resolve_time_slots(places_per_day)
    app = current_app._get_current_object()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_itinerary = executor.submit(
            run_in_context, app, _build_itinerary_rows,
            trip, destinations, day_distribution, all_preferences, time_slots, regeneration_seed
        )
        future_hotels = executor.submit(
            run_in_context, app, recommended_hotels,
            destinations, trip.state_country, 6, False, None, None
        )
        
        itinerary_rows, _total_activity_cost = future_itinerary.result()
        hotels = future_hotels.result()

    average_hotel_rate = 2500.0
    if hotels:
        average_hotel_rate = sum((h.price_min + h.price_max) / 2 for h in hotels) / len(hotels)

    budget = _calculate_budget_for_rows(
        trip=trip,
        destinations=destinations,
        average_hotel_rate=average_hotel_rate,
        itinerary_rows=itinerary_rows,
    )

    return {
        "destinations": destinations,
        "day_distribution": day_distribution,
        "itinerary_rows": itinerary_rows,
        "budget": budget,
        "average_hotel_rate": average_hotel_rate,
    }


def _snapshot_existing_rows_for_days(trip: Trip, keep_days: set[int]) -> list[dict]:
    destinations = parse_destinations(trip.destinations_raw)
    fallback_destination = destinations[0] if destinations else trip.state_country
    preserved = []
    for item in trip.itineraries:
        if item.day_number not in keep_days:
            continue
        preserved.append(
            {
                "destination_name": item.destination.name if item.destination else fallback_destination,
                "day_number": item.day_number,
                "time_slot": item.time_slot,
                "title": item.title,
                "description": item.description,
                "ticket_price": float(item.ticket_price or 0),
                "weather_summary": item.weather_summary,
                "map_link": item.map_link,
                "rating": float(item.rating or 4.0),
                "category": "custom",
                "latitude": item.latitude,
                "longitude": item.longitude,
            }
        )
    return sorted(preserved, key=lambda x: (x["day_number"], _time_slot_rank(x["time_slot"]), x["title"]))


def _merge_preserved_days(plan_data: dict, preserved_rows: list[dict], keep_days: set[int], day_limit: int) -> dict:
    if not keep_days or not preserved_rows:
        return plan_data

    filtered_preserved = [row for row in preserved_rows if 1 <= int(row["day_number"]) <= day_limit]
    regenerated_rows = [row for row in plan_data["itinerary_rows"] if int(row["day_number"]) not in keep_days]
    merged_rows = regenerated_rows + filtered_preserved
    merged_rows.sort(key=lambda x: (int(x["day_number"]), _time_slot_rank(x["time_slot"]), str(x["title"]).lower()))
    plan_data["itinerary_rows"] = merged_rows
    plan_data["budget"] = _calculate_budget_for_rows(
        trip=plan_data["trip"],
        destinations=plan_data["destinations"],
        average_hotel_rate=plan_data["average_hotel_rate"],
        itinerary_rows=merged_rows,
    )
    return plan_data


def _apply_plan_data(trip: Trip, plan_data: dict, clear_existing: bool) -> None:
    destinations = plan_data["destinations"]
    day_distribution = plan_data["day_distribution"]
    itinerary_rows = plan_data["itinerary_rows"]
    budget = plan_data["budget"]

    if clear_existing:
        clear_existing_plan(trip)

    destination_records = []
    destination_records_by_name = {}
    for idx, destination_name in enumerate(destinations):
        destination_record = Destination(
            trip_id=trip.id,
            name=destination_name,
            order_index=idx + 1,
            allocated_days=day_distribution[idx],
        )
        db.session.add(destination_record)
        destination_records.append(destination_record)
        destination_records_by_name[destination_name.strip().lower()] = destination_record
    db.session.flush()

    for row in itinerary_rows:
        destination_record = None
        destination_index = row.get("destination_index")
        if isinstance(destination_index, int) and 0 <= destination_index < len(destination_records):
            destination_record = destination_records[destination_index]

        if not destination_record:
            destination_name_key = str(row.get("destination_name", "")).strip().lower()
            destination_record = destination_records_by_name.get(destination_name_key)

        if not destination_record and destination_records:
            destination_record = destination_records[0]

        db.session.add(
            Itinerary(
                trip_id=trip.id,
                destination_id=destination_record.id if destination_record else None,
                day_number=int(row["day_number"]),
                time_slot=str(row["time_slot"]).strip() or "Morning",
                title=row["title"],
                description=row["description"],
                ticket_price=float(row.get("ticket_price", 0) or 0),
                weather_summary=row.get("weather_summary"),
                map_link=row.get("map_link"),
                rating=float(row.get("rating", 4.0) or 4.0),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
            )
        )
        db.session.add(
            Activity(
                trip_id=trip.id,
                destination=destination_record.name if destination_record else str(row.get("destination_name", "")).strip(),
                name=row["title"],
                category=row.get("category", "cultural"),
                expected_cost=float(row.get("ticket_price", 0) or 0),
            )
        )

    trip.transport_cost = budget["transport_cost"]
    trip.hotel_cost = budget["hotel_cost"]
    trip.food_cost = budget["food_cost"]
    trip.service_charge = budget.get("service_charge", trip.service_charge)
    trip.activity_cost = budget["activity_cost"]
    trip.per_person_cost = budget["per_person_cost"]
    trip.total_group_cost = budget["total_group_cost"]
    trip.predicted_budget = budget["predicted_budget"]
    trip.itinerary_summary = f"{trip.number_of_days}-day itinerary across {len(destinations)} destination(s)."

    db.session.flush()


def recalculate_trip_costs_from_current_itinerary(trip: Trip) -> Trip:
    ensure_trip_cost_floor_values(trip)
    activity_total = sum(float(item.ticket_price or 0) for item in trip.itineraries)
    trip.activity_cost = round(activity_total, 2)
    trip.total_group_cost = round(
        float(trip.transport_cost or 0)
        + float(trip.hotel_cost or 0)
        + float(trip.food_cost or 0)
        + float(trip.activity_cost or 0)
        + float(trip.service_charge or 0),
        2,
    )
    trip.per_person_cost = round(trip.total_group_cost / max(1, int(trip.number_of_people or 1)), 2)
    return trip


def ensure_trip_cost_floor_values(trip: Trip) -> bool:
    changed = False
    days = max(1, int(trip.number_of_days or 1))
    people = max(1, int(trip.number_of_people or 1))
    rooms = max(1, math.ceil(people / 2))

    min_hotel_cost = MIN_HOTEL_DAILY_PER_ROOM * days * rooms
    min_food_cost = MIN_FOOD_DAILY_PER_PERSON * days * people

    if float(trip.hotel_cost or 0) <= 0:
        trip.hotel_cost = round(min_hotel_cost, 2)
        changed = True
    if float(trip.food_cost or 0) <= 0:
        trip.food_cost = round(min_food_cost, 2)
        changed = True
    if float(trip.service_charge or 0) <= 0:
        trip.service_charge = round(MIN_SERVICE_CHARGE, 2)
        changed = True

    if changed:
        trip.total_group_cost = round(
            float(trip.transport_cost or 0)
            + float(trip.hotel_cost or 0)
            + float(trip.food_cost or 0)
            + float(trip.activity_cost or 0)
            + float(trip.service_charge or 0),
            2,
        )
        trip.per_person_cost = round(trip.total_group_cost / max(1, people), 2)

    return changed


def clear_existing_plan(trip: Trip):
    def _delete_existing():
        Itinerary.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
        Activity.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
        Destination.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)

    _run_with_db_retry(_delete_existing)


def generate_trip_plan(trip: Trip, regeneration_seed: int | None = None, places_per_day: int | None = None):
    plan_data = _prepare_plan_data(trip, regeneration_seed=regeneration_seed, places_per_day=places_per_day)
    _apply_plan_data(trip, plan_data, clear_existing=True)


def create_trip_from_form(data: dict, traveler_id=None, agent_id=None, client_id=None):
    trip_kwargs = {
        "title": f"{data['destinations'][0]} Adventure" if data["destinations"] else "Custom Trip",
        "from_location": data["from_location"].split(",")[0].strip(),
        "destinations_raw": ", ".join(data["destinations"]),
        "state_country": data["state_country"],
        "start_date": data["start_date"],
        "number_of_days": data["number_of_days"],
        "number_of_people": data["number_of_people"],
        "budget": data["budget"],
        "travel_mode": data["travel_mode"],
        "travel_type": data["travel_type"],
        "traveler_id": traveler_id,
        "agent_id": agent_id,
        "client_id": client_id,
        "status": data.get("status", "draft"),
        "service_charge": data.get("service_charge", 0.0),
    }
    preferences = data.get("preferences", [])
    places_per_day = int(data.get("places_per_day", 4) or 4)

    template_trip = Trip(**trip_kwargs)
    template_trip.preferences = preferences
    plan_data = _prepare_plan_data(template_trip, places_per_day=places_per_day)

    for attempt in range(8):
        trip = Trip(**trip_kwargs)
        trip.preferences = preferences
        try:
            db.session.add(trip)
            db.session.flush()
            _apply_plan_data(trip, plan_data, clear_existing=False)
            db.session.commit()
            return trip
        except OperationalError as exc:
            if _is_sqlite_locked_error(exc) and attempt < 7:
                db.session.rollback()
                time.sleep(0.35 * (attempt + 1))
                continue
            raise


def regenerate_trip(
    trip: Trip,
    service_charge: float | None = None,
    keep_days: set[int] | None = None,
    number_of_days: int | None = None,
    number_of_people: int | None = None,
    places_per_day: int | None = None,
):
    for attempt in range(8):
        try:
            if service_charge is not None:
                trip.service_charge = service_charge
            if number_of_days is not None:
                trip.number_of_days = int(number_of_days)
            if number_of_people is not None:
                trip.number_of_people = int(number_of_people)

            safe_keep_days = {int(day) for day in (keep_days or set()) if int(day) > 0 and int(day) <= trip.number_of_days}
            preserved_rows = _snapshot_existing_rows_for_days(trip, safe_keep_days) if safe_keep_days else []
            effective_places_per_day = places_per_day if places_per_day is not None else infer_places_per_day(trip, fallback=4)

            plan_data = _prepare_plan_data(
                trip,
                regeneration_seed=time.time_ns(),
                places_per_day=effective_places_per_day,
            )
            plan_data["trip"] = trip
            plan_data = _merge_preserved_days(plan_data, preserved_rows, safe_keep_days, trip.number_of_days)
            plan_data.pop("trip", None)

            _apply_plan_data(trip, plan_data, clear_existing=True)
            db.session.commit()
            return trip
        except OperationalError as exc:
            if _is_sqlite_locked_error(exc) and attempt < 7:
                db.session.rollback()
                time.sleep(0.35 * (attempt + 1))
                continue
            raise
