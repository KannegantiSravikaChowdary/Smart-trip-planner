from datetime import datetime, timedelta, date
from urllib.parse import quote

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import Booking, Client, Hotel, Itinerary, ItineraryEditRequest, Trip, TripUpdateRequest, User
from app.services.authz import role_required
from app.services.form_service import parse_trip_form, validate_trip_payload
from app.services.food_data_service import append_food_feedback
from app.services.hotel_service import get_live_hotel_availability, recommended_hotels
from app.services.itinerary_approval_service import pending_request_map, pending_requests_for_trip
from app.services.place_service import build_maps_link
from app.services.trip_service import (
    create_trip_from_form,
    ensure_trip_cost_floor_values,
    infer_places_per_day,
    parse_destinations,
    regenerate_trip,
)
from app.services.validation_service import is_valid_full_name, is_valid_phone
from app.services.whatsapp_service import send_trip_whatsapp_notifications


agent_bp = Blueprint("agent", __name__)
TIME_SLOT_ORDER = {
    "Early Morning": 0,
    "Morning": 1,
    "Afternoon": 2,
    "Evening": 3,
    "Night": 4,
    "Late Night": 5,
}


def _itinerary_sort_key(item):
    return (item.day_number, TIME_SLOT_ORDER.get(item.time_slot, 99), item.time_slot)


@agent_bp.route("/dashboard")
@login_required
@role_required("agent")
def dashboard():
    clients = Client.query.filter_by(agent_id=current_user.id).all()
    trips = Trip.query.filter_by(agent_id=current_user.id).all()
    bookings = (
        Booking.query.join(Trip, Booking.trip_id == Trip.id)
        .filter(Trip.agent_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )

    upcoming_trips = [trip for trip in trips if trip.status in {"sent", "confirmed", "in_progress"}]
    revenue = sum(trip.total_group_cost for trip in trips)

    return render_template(
        "agent/dashboard.html",
        total_clients=len(clients),
        total_trips=len(trips),
        total_bookings=len(bookings),
        upcoming_trips=len(upcoming_trips),
        total_revenue=round(revenue, 2),
        recent_activity=(trips + bookings)[:8],
        bookings=bookings[:5],
        clients=sorted(clients, key=lambda item: item.created_at, reverse=True)[:8],
    )


@agent_bp.route("/clients")
@login_required
@role_required("agent")
def clients():
    client_list = Client.query.filter_by(agent_id=current_user.id).order_by(Client.created_at.desc()).all()
    return render_template("agent/clients.html", clients=client_list)


@agent_bp.route("/clients/add", methods=["POST"])
@login_required
@role_required("agent")
def add_client():
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()

    if not full_name:
        flash("Client name is required.", "danger")
        return redirect(url_for("agent.clients"))
    if not is_valid_full_name(full_name):
        flash("Enter a valid client name.", "danger")
        return redirect(url_for("agent.clients"))
    if phone and not is_valid_phone(phone):
        flash("Enter a valid phone number.", "danger")
        return redirect(url_for("agent.clients"))

    client = Client(
        full_name=full_name,
        # Email removed from client UI; keep DB compatibility with non-null column.
        email="",
        phone=phone or None,
        notes=request.form.get("notes", "").strip(),
        agent_id=current_user.id,
    )
    db.session.add(client)
    db.session.commit()
    flash("Client added.", "success")
    return redirect(url_for("agent.clients"))


@agent_bp.route("/clients/<int:client_id>/edit", methods=["POST"])
@login_required
@role_required("agent")
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if client.agent_id != current_user.id:
        abort(403)

    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", client.phone or "").strip()
    if not full_name:
        flash("Client name is required.", "danger")
        return redirect(url_for("agent.clients"))
    if not is_valid_full_name(full_name):
        flash("Enter a valid client name.", "danger")
        return redirect(url_for("agent.clients"))
    if phone and not is_valid_phone(phone):
        flash("Enter a valid phone number.", "danger")
        return redirect(url_for("agent.clients"))

    client.full_name = full_name
    client.phone = phone or None
    client.notes = request.form.get("notes", client.notes or "").strip()
    db.session.commit()

    flash("Client updated.", "success")
    return redirect(url_for("agent.clients"))


@agent_bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
@role_required("agent")
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    if client.agent_id != current_user.id:
        abort(403)

    db.session.delete(client)
    db.session.commit()
    flash("Client deleted.", "info")
    return redirect(url_for("agent.clients"))


@agent_bp.route("/trips")
@login_required
@role_required("agent")
def trips():
    trip_list = Trip.query.filter_by(agent_id=current_user.id).order_by(Trip.created_at.desc()).all()
    # Compatibility guard: prevents template crash if a stale template references `trip` outside loop.
    return render_template("agent/trips.html", trips=trip_list, trip=None)


@agent_bp.route("/trips/new", methods=["GET", "POST"])
@login_required
@role_required("agent")
def create_trip():
    client_list = Client.query.filter_by(agent_id=current_user.id).all()

    if request.method == "POST":
        try:
            payload = parse_trip_form(request.form)
        except ValueError:
            flash("Invalid trip form values.", "danger")
            return redirect(url_for("agent.create_trip"))

        is_valid, message = validate_trip_payload(payload)
        if not is_valid:
            flash(message, "danger")
            return redirect(url_for("agent.create_trip"))

        client_id = request.form.get("client_id")
        if not client_id:
            flash("Client selection is required.", "danger")
            return redirect(url_for("agent.create_trip"))
            
        try:
            client = Client.query.get(int(client_id))
            if not client or client.agent_id != current_user.id:
                flash("Invalid client selected.", "danger")
                return redirect(url_for("agent.create_trip"))
            client_id = client.id
        except ValueError:
            flash("Invalid client selected.", "danger")
            return redirect(url_for("agent.create_trip"))

        traveler_id = None

        payload["status"] = request.form.get("status", "draft").lower()
        try:
            trip = create_trip_from_form(payload, agent_id=current_user.id, client_id=client_id, traveler_id=traveler_id)
        except RuntimeError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("agent.create_trip"))
        except OperationalError as exc:
            db.session.rollback()
            current_app.logger.warning("Agent trip create failed due to DB operational error: %s", exc)
            flash("Database is busy. Please retry trip generation in a few seconds.", "danger")
            return redirect(url_for("agent.create_trip"))
        sent, targets = send_trip_whatsapp_notifications(trip, "Trip created by agent")
        if targets:
            current_app.logger.info("Agent trip create WhatsApp sent to %s/%s targets", sent, targets)
        flash("Client trip generated.", "success")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    return render_template("agent/create_trip.html", clients=client_list)


@agent_bp.route("/trips/<int:trip_id>")
@login_required
@role_required("agent")
def view_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)


    # New bookings are disabled for completed trips check is in create_booking POST route.
    # No redirect here to avoid infinite loops.
    if ensure_trip_cost_floor_values(trip):
        db.session.commit()

    destinations = parse_destinations(trip.destinations_raw)
    itinerary_by_day = {}
    for item in sorted(trip.itineraries, key=_itinerary_sort_key):
        itinerary_by_day.setdefault(item.day_number, []).append(item)
    pending_by_itinerary = pending_request_map(trip.id)
    pending_requests = pending_requests_for_trip(trip.id)
    pending_trip_update = (
        TripUpdateRequest.query.filter_by(trip_id=trip.id, status="pending")
        .order_by(TripUpdateRequest.created_at.desc())
        .first()
    )

    checkin_date = trip.start_date.isoformat()
    checkout_date = (trip.start_date + timedelta(days=max(1, int(trip.number_of_days)))).isoformat()
    hotels = recommended_hotels(
        destinations,
        state_country=trip.state_country,
        persist=True,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
    )
    trip_bookings = Booking.query.filter_by(trip_id=trip.id).order_by(Booking.created_at.desc()).all()

    trip_url = url_for("agent.view_trip", trip_id=trip.id, _external=True)
    whatsapp_text = (
        f"Trip Plan: {trip.title}\n"
        f"Destinations: {trip.destinations_raw}\n"
        f"Days: {trip.number_of_days} | Travelers: {trip.number_of_people}\n"
        f"Estimated Total: {trip.total_group_cost}\n"
        f"Details: {trip_url}"
    )
    whatsapp_link = f"https://wa.me/?text={quote(whatsapp_text)}"
    email_template = f"Subject: Trip Plan - {trip.title}\n\nAttached itinerary for your review."

    return render_template(
        "agent/trip_detail.html",
        trip=trip,
        itinerary_by_day=itinerary_by_day,
        hotels=hotels,
        destinations=destinations,
        bookings=trip_bookings,
        whatsapp_link=whatsapp_link,
        email_template=email_template,
        places_per_day=infer_places_per_day(trip, fallback=4),
        pending_by_itinerary=pending_by_itinerary,
        pending_requests=pending_requests,
        pending_trip_update=pending_trip_update,
    )


@agent_bp.route("/trips/<int:trip_id>/update", methods=["POST"])
@login_required
@role_required("agent")
def update_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    if trip.status == "completed":
        flash("New bookings are disabled for completed trips.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
        abort(403)

    trip.status = request.form.get("status", trip.status).lower()
    service_charge = request.form.get("service_charge")
    if service_charge is not None:
        trip.service_charge = float(service_charge or 0)
    number_of_days = request.form.get("number_of_days", "").strip()
    number_of_people = request.form.get("number_of_people", "").strip()
    places_per_day = request.form.get("places_per_day", "").strip()

    try:
        updated_days = int(number_of_days or trip.number_of_days)
        updated_people = int(number_of_people or trip.number_of_people)
        updated_places_per_day = int(places_per_day or infer_places_per_day(trip, fallback=4))
    except ValueError:
        flash("Invalid update inputs.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    destinations = parse_destinations(trip.destinations_raw)
    if updated_days < len(destinations):
        flash("Number of days must be at least equal to destination count.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
    if updated_days <= 0 or updated_people <= 0:
        flash("Days and travelers must be greater than zero.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
    if updated_places_per_day < 3 or updated_places_per_day > 6:
        flash("Places per day must be between 3 and 6.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    pending_update = (
        TripUpdateRequest.query.filter_by(trip_id=trip.id, status="pending")
        .order_by(TripUpdateRequest.created_at.desc())
        .first()
    )
    if pending_update:
        pending_update.proposed_status = trip.status
        pending_update.proposed_service_charge = float(trip.service_charge or 0)
        pending_update.proposed_number_of_days = updated_days
        pending_update.proposed_number_of_people = updated_people
        pending_update.proposed_places_per_day = updated_places_per_day
    else:
        db.session.add(
            TripUpdateRequest(
                trip_id=trip.id,
                agent_id=current_user.id,
                status="pending",
                proposed_status=trip.status,
                proposed_service_charge=float(trip.service_charge or 0),
                proposed_number_of_days=updated_days,
                proposed_number_of_people=updated_people,
                proposed_places_per_day=updated_places_per_day,
            )
        )
    trip.status = "sent"
    db.session.commit()
    sent, targets = send_trip_whatsapp_notifications(trip, "Trip updated by agent")
    if targets:
        current_app.logger.info("Agent trip update WhatsApp sent to %s/%s targets", sent, targets)
    flash("Trip update request sent for traveler approval.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/trips/<int:trip_id>/start", methods=["POST"])
@login_required
@role_required("agent")
def start_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    if trip.status == "completed":
        flash("New bookings are disabled for completed trips.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
        abort(403)

    trip.status = "in_progress"
    db.session.commit()
    send_trip_whatsapp_notifications(trip, "Trip started")
    flash("Trip marked as In Progress.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/trips/<int:trip_id>/end", methods=["POST"])
@login_required
@role_required("agent")
def end_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    if trip.status == "completed":
        flash("New bookings are disabled for completed trips.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
        abort(403)

    trip.status = "completed"
    db.session.commit()
    send_trip_whatsapp_notifications(trip, "Trip completed")
    flash("Trip marked as Completed.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/itinerary/<int:item_id>/update", methods=["POST"])
@login_required
@role_required("agent")
def update_itinerary(item_id):
    item = Itinerary.query.get_or_404(item_id)
    trip = Trip.query.get_or_404(item.trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    proposed_title = request.form.get("title", item.title).strip() or item.title
    proposed_description = request.form.get("description", item.description).strip() or item.description
    ticket_value = request.form.get("ticket_price", "").strip()
    proposed_ticket_price = item.ticket_price
    if ticket_value != "":
        proposed_ticket_price = float(ticket_value)
    map_query = request.form.get("map_query", "").strip()
    proposed_map_link = build_maps_link(map_query) if map_query else request.form.get("map_link", item.map_link)
    if not proposed_map_link:
        proposed_map_link = build_maps_link(f"{proposed_title}, {trip.state_country}")

    existing_pending = ItineraryEditRequest.query.filter_by(
        trip_id=trip.id,
        itinerary_id=item.id,
        status="pending",
    ).first()

    if existing_pending:
        existing_pending.proposed_title = proposed_title
        existing_pending.proposed_description = proposed_description
        existing_pending.proposed_ticket_price = float(proposed_ticket_price or 0)
        existing_pending.proposed_map_link = proposed_map_link
        request_id = existing_pending.id
    else:
        pending_request = ItineraryEditRequest(
            trip_id=trip.id,
            itinerary_id=item.id,
            agent_id=current_user.id,
            status="pending",
            proposed_title=proposed_title,
            proposed_description=proposed_description,
            proposed_ticket_price=float(proposed_ticket_price or 0),
            proposed_map_link=proposed_map_link,
        )
        db.session.add(pending_request)
        db.session.flush()
        request_id = pending_request.id

    trip.status = "sent"
    db.session.commit()
    send_trip_whatsapp_notifications(trip, f"Itinerary edit requested (Request #{request_id})")

    flash("Itinerary edit request sent for traveler approval.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/itinerary/requests/<int:request_id>/cancel", methods=["POST"])
@login_required
@role_required("agent")
def cancel_itinerary_request(request_id):
    edit_request = ItineraryEditRequest.query.get_or_404(request_id)
    trip = Trip.query.get_or_404(edit_request.trip_id)
    if trip.agent_id != current_user.id:
        abort(403)
    if edit_request.status != "pending":
        flash("Only pending requests can be cancelled.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    edit_request.status = "rejected"
    edit_request.reviewer_id = current_user.id
    edit_request.reviewed_at = datetime.utcnow()
    if not ItineraryEditRequest.query.filter_by(trip_id=trip.id, status="pending").first():
        trip.status = "confirmed"
    db.session.commit()
    flash("Pending itinerary request cancelled.", "info")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/trips/<int:trip_id>/delete", methods=["POST"])
@login_required
@role_required("agent")
def delete_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)


    # No status check for deletion.

    db.session.delete(trip)
    db.session.commit()
    flash("Trip deleted.", "info")
    return redirect(url_for("agent.trips"))


@agent_bp.route("/trips/<int:trip_id>/bookings", methods=["POST"])
@login_required
@role_required("agent")
def create_booking(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    if trip.status == "completed":
        flash("New bookings are disabled for completed trips.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
        abort(403)

    hotel = Hotel.query.get_or_404(int(request.form.get("hotel_id")))
    checkin = request.form.get("checkin_date")
    checkout = request.form.get("checkout_date")

    try:
        checkin_date_obj = datetime.strptime(checkin, "%Y-%m-%d").date() if checkin else trip.start_date
        checkout_date_obj = datetime.strptime(checkout, "%Y-%m-%d").date() if checkout else (
            checkin_date_obj + timedelta(days=1)
        )
        
        if checkin_date_obj >= checkout_date_obj:
            flash("Check-out date must be after check-in date.", "danger")
            return redirect(url_for("agent.view_trip", trip_id=trip.id))
            
        if checkin_date_obj < date.today():
            flash("Check-in date cannot be in the past.", "danger")
            return redirect(url_for("agent.view_trip", trip_id=trip.id))

        if checkin_date_obj < trip.start_date:
            flash(f"Check-in date cannot be before the trip start date ({trip.start_date}).", "danger")
            return redirect(url_for("agent.view_trip", trip_id=trip.id))

    except ValueError:
        flash("Invalid booking dates. Please use YYYY-MM-DD format.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    availability_status, _rooms = get_live_hotel_availability(
        hotel_name=hotel.name,
        city=hotel.city,
        state_country=trip.state_country,
        checkin_date=checkin_date_obj.isoformat(),
        checkout_date=checkout_date_obj.isoformat(),
    )
    if availability_status == "Sold Out":
        flash("Selected hotel is sold out for the chosen dates. Please pick another hotel.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    booking = Booking(
        trip_id=trip.id,
        hotel_id=hotel.id,
        client_id=trip.client_id,
        checkin_date=checkin_date_obj if checkin else None,
        checkout_date=checkout_date_obj if checkout else None,
        reference_number=request.form.get("reference_number", "").strip() or None,
        status=request.form.get("status", "pending").lower(),
        payment_status=request.form.get("payment_status", "pending").lower(),
        total_price=float(request.form.get("total_price", 0) or 0),
    )

    db.session.add(booking)
    db.session.commit()
    send_trip_whatsapp_notifications(trip, "Hotel booking updated by agent")
    flash("Booking saved.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/bookings")
@login_required
@role_required("agent")
def bookings():
    all_bookings = (
        Booking.query.join(Trip, Booking.trip_id == Trip.id)
        .filter(Trip.agent_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )

    upcoming_checkins = [booking for booking in all_bookings if booking.checkin_date and booking.status != "cancelled"]
    return render_template(
        "agent/bookings.html",
        bookings=all_bookings,
        total_bookings=len(all_bookings),
        upcoming_checkins=len(upcoming_checkins),
    )


@agent_bp.route("/bookings/<int:booking_id>/update", methods=["POST"])
@login_required
@role_required("agent")
def update_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    trip = Trip.query.get_or_404(booking.trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    booking.reference_number = request.form.get("reference_number", booking.reference_number)
    booking.status = request.form.get("status", booking.status).lower()
    
    # If agent is confirming a booking that was pending payment verification
    old_payment_status = booking.payment_status
    new_payment_status = request.form.get("payment_status", booking.payment_status).lower()
    booking.payment_status = new_payment_status
    booking.total_price = float(request.form.get("total_price", booking.total_price) or booking.total_price)

    db.session.commit()
    
    if old_payment_status != "paid" and new_payment_status == "paid":
        # Notification: Payment confirmed
        send_trip_whatsapp_notifications(trip, f"Great news! Your payment for booking #{booking.id} ({booking.hotel.name}) has been verified and confirmed.")
        flash(f"Payment for booking #{booking.id} confirmed. Traveler has been notified.", "success")
    else:
        flash("Booking updated.", "success")
        
    return redirect(url_for("agent.bookings"))


@agent_bp.route("/trips/<int:trip_id>/food-feedback", methods=["POST"])
@login_required
@role_required("agent")
def submit_food_feedback(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)


    # Allow food feedback for completed trips.

    actual_food_cost_raw = request.form.get("actual_food_cost", "").strip()
    actual_total_cost_raw = request.form.get("actual_total_cost", "").strip()
    if not actual_food_cost_raw:
        flash("Please enter actual food cost.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    try:
        actual_food_cost = float(actual_food_cost_raw)
        actual_total_cost = float(actual_total_cost_raw) if actual_total_cost_raw else None
    except ValueError:
        flash("Invalid numeric values for actual costs.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    if actual_food_cost <= 0:
        flash("Actual food cost must be greater than zero.", "danger")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    append_food_feedback(
        trip,
        actual_food_cost=actual_food_cost,
        actual_total_cost=actual_total_cost,
        source_role="agent",
    )
    flash("Actual food costs recorded for machine learning improvement.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))


@agent_bp.route("/trips/<int:trip_id>/accept-interest", methods=["POST"])
@login_required
@role_required("agent")
def accept_interest(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.agent_id != current_user.id:
        abort(403)

    if trip.status == "completed":
        flash("New bookings are disabled for completed trips.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))
        abort(403)
        
    if trip.status != "liked":
        flash("Trip interest can only be accepted if the traveler liked it.", "warning")
        return redirect(url_for("agent.view_trip", trip_id=trip.id))

    trip.status = "confirmed"
    db.session.commit()
    
    # Notify traveler via WhatsApp
    send_trip_whatsapp_notifications(trip, f"The agent ({current_user.full_name}) has accepted your interest and now the trip is confirmed!")
    
    flash("Interest accepted. Trip is now confirmed.", "success")
    return redirect(url_for("agent.view_trip", trip_id=trip.id))
