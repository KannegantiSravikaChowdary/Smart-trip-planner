from __future__ import annotations

import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    whatsapp_opt_in = db.Column(db.Boolean, nullable=False, default=True)
    google_sub = db.Column(db.String(255), nullable=True, unique=True, index=True)
    role = db.Column(db.String(20), nullable=False, default="traveler")

    traveler_trips = db.relationship(
        "Trip",
        foreign_keys="Trip.traveler_id",
        back_populates="traveler",
        cascade="all, delete-orphan",
    )
    managed_trips = db.relationship(
        "Trip",
        foreign_keys="Trip.agent_id",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    clients = db.relationship("Client", back_populates="agent", cascade="all, delete-orphan")
    traveler_links = db.relationship(
        "AgentTraveler",
        foreign_keys="AgentTraveler.agent_id",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    agent_links = db.relationship(
        "AgentTraveler",
        foreign_keys="AgentTraveler.traveler_id",
        back_populates="traveler",
        cascade="all, delete-orphan",
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_agent(self) -> bool:
        return self.role == "agent"


class Client(TimestampMixin, db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True, default="")
    phone = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    agent = db.relationship("User", back_populates="clients")
    trips = db.relationship("Trip", back_populates="client", cascade="all, delete-orphan")


class AgentTraveler(TimestampMixin, db.Model):
    __tablename__ = "agent_travelers"
    __table_args__ = (db.UniqueConstraint("agent_id", "traveler_id", name="uq_agent_traveler_pair"),)

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    agent = db.relationship("User", foreign_keys=[agent_id], back_populates="traveler_links")
    traveler = db.relationship("User", foreign_keys=[traveler_id], back_populates="agent_links")


class Trip(TimestampMixin, db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    from_location = db.Column(db.String(120), nullable=False)
    state_country = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    number_of_days = db.Column(db.Integer, nullable=False)
    number_of_people = db.Column(db.Integer, nullable=False)
    budget = db.Column(db.Float, nullable=False)
    travel_mode = db.Column(db.String(20), nullable=False)
    travel_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    destinations_raw = db.Column(db.Text, nullable=False)
    preferences_json = db.Column(db.Text, nullable=False, default="[]")
    itinerary_summary = db.Column(db.Text, nullable=True)

    service_charge = db.Column(db.Float, nullable=False, default=0.0)
    transport_cost = db.Column(db.Float, nullable=False, default=0.0)
    hotel_cost = db.Column(db.Float, nullable=False, default=0.0)
    food_cost = db.Column(db.Float, nullable=False, default=0.0)
    activity_cost = db.Column(db.Float, nullable=False, default=0.0)
    per_person_cost = db.Column(db.Float, nullable=False, default=0.0)
    total_group_cost = db.Column(db.Float, nullable=False, default=0.0)
    predicted_budget = db.Column(db.Float, nullable=False, default=0.0)
    
    # Post-trip Traveler Feedback
    feedback_rating = db.Column(db.Integer, nullable=True)
    feedback_text = db.Column(db.Text, nullable=True)

    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)

    traveler = db.relationship("User", foreign_keys=[traveler_id], back_populates="traveler_trips")
    agent = db.relationship("User", foreign_keys=[agent_id], back_populates="managed_trips")
    client = db.relationship("Client", back_populates="trips")
    destinations = db.relationship("Destination", back_populates="trip", cascade="all, delete-orphan")
    itineraries = db.relationship("Itinerary", back_populates="trip", cascade="all, delete-orphan")
    activities = db.relationship("Activity", back_populates="trip", cascade="all, delete-orphan")
    bookings = db.relationship("Booking", back_populates="trip", cascade="all, delete-orphan")
    itinerary_edit_requests = db.relationship(
        "ItineraryEditRequest",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    notification_logs = db.relationship(
        "NotificationLog",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    update_requests = db.relationship(
        "TripUpdateRequest",
        back_populates="trip",
        cascade="all, delete-orphan",
    )

    @property
    def preferences(self) -> list[str]:
        try:
            return json.loads(self.preferences_json or "[]")
        except json.JSONDecodeError:
            return []

    @preferences.setter
    def preferences(self, values: list[str]) -> None:
        self.preferences_json = json.dumps(values)


class Destination(TimestampMixin, db.Model):
    __tablename__ = "destinations"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=1)
    allocated_days = db.Column(db.Integer, nullable=False, default=1)

    trip = db.relationship("Trip", back_populates="destinations")


class Itinerary(TimestampMixin, db.Model):
    __tablename__ = "itineraries"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    destination_id = db.Column(db.Integer, db.ForeignKey("destinations.id"), nullable=True, index=True)
    day_number = db.Column(db.Integer, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    ticket_price = db.Column(db.Float, nullable=False, default=0.0)
    weather_summary = db.Column(db.String(120), nullable=True)
    map_link = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Float, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    trip = db.relationship("Trip", back_populates="itineraries")
    destination = db.relationship("Destination")
    edit_requests = db.relationship("ItineraryEditRequest", back_populates="itinerary", cascade="all, delete-orphan")


class Hotel(TimestampMixin, db.Model):
    __tablename__ = "hotels"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    city = db.Column(db.String(80), nullable=False, index=True)
    address = db.Column(db.String(255), nullable=False)
    price_min = db.Column(db.Float, nullable=False)
    price_max = db.Column(db.Float, nullable=False)
    rating = db.Column(db.Float, nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    map_link = db.Column(db.String(255), nullable=False)

    bookings = db.relationship("Booking", back_populates="hotel")


class Booking(TimestampMixin, db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey("hotels.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)
    checkin_date = db.Column(db.Date, nullable=True)
    checkout_date = db.Column(db.Date, nullable=True)
    reference_number = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    utr_number = db.Column(db.String(100), nullable=True)
    payment_screenshot = db.Column(db.String(255), nullable=True)
    total_price = db.Column(db.Float, nullable=False, default=0.0)

    trip = db.relationship("Trip", back_populates="bookings")
    hotel = db.relationship("Hotel", back_populates="bookings")
    payments = db.relationship("Payment", back_populates="booking", cascade="all, delete-orphan")


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    paid_at = db.Column(db.DateTime, nullable=True)

    booking = db.relationship("Booking", back_populates="payments")


class Activity(TimestampMixin, db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    destination = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False)
    expected_cost = db.Column(db.Float, nullable=False, default=0.0)

    trip = db.relationship("Trip", back_populates="activities")


class ItineraryEditRequest(TimestampMixin, db.Model):
    __tablename__ = "itinerary_edit_requests"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    itinerary_id = db.Column(db.Integer, db.ForeignKey("itineraries.id"), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    proposed_title = db.Column(db.String(160), nullable=False)
    proposed_description = db.Column(db.Text, nullable=False)
    proposed_ticket_price = db.Column(db.Float, nullable=False, default=0.0)
    proposed_map_link = db.Column(db.String(255), nullable=True)
    proposed_latitude = db.Column(db.Float, nullable=True)
    proposed_longitude = db.Column(db.Float, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    trip = db.relationship("Trip", back_populates="itinerary_edit_requests")
    itinerary = db.relationship("Itinerary", back_populates="edit_requests")
    agent = db.relationship("User", foreign_keys=[agent_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


class NotificationLog(TimestampMixin, db.Model):
    __tablename__ = "notification_logs"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    target_phone = db.Column(db.String(30), nullable=False)
    channel = db.Column(db.String(30), nullable=False, default="whatsapp")
    event_label = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="failed")
    provider_message_id = db.Column(db.String(80), nullable=True)
    error_message = db.Column(db.String(255), nullable=True)

    trip = db.relationship("Trip", back_populates="notification_logs")


class TripUpdateRequest(TimestampMixin, db.Model):
    __tablename__ = "trip_update_requests"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")

    proposed_status = db.Column(db.String(20), nullable=False, default="draft")
    proposed_service_charge = db.Column(db.Float, nullable=False, default=0.0)
    proposed_number_of_days = db.Column(db.Integer, nullable=False, default=1)
    proposed_number_of_people = db.Column(db.Integer, nullable=False, default=1)
    proposed_places_per_day = db.Column(db.Integer, nullable=False, default=4)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    trip = db.relationship("Trip", back_populates="update_requests")
    agent = db.relationship("User", foreign_keys=[agent_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))
