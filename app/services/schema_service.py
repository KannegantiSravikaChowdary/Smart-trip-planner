from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy import text

from app.extensions import db


def _table_exists(table_name: str) -> bool:
    return inspect(db.engine).has_table(table_name)


def _table_columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {str(row.get("name", "")).strip().lower() for row in rows}


def _add_column_if_missing(table_name: str, column_name: str, ddl_type: str) -> None:
    if not _table_exists(table_name):
        return
    columns = _table_columns(table_name)
    if column_name.lower() in columns:
        return
    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"))


def ensure_sqlite_schema_updates() -> None:
    db_uri = str(db.engine.url)
    if not db_uri.startswith("sqlite"):
        return

    _add_column_if_missing("users", "phone", "VARCHAR(30)")
    _add_column_if_missing("users", "whatsapp_opt_in", "BOOLEAN NOT NULL DEFAULT 1")
    _add_column_if_missing("users", "google_sub", "VARCHAR(255)")
    
    _add_column_if_missing("bookings", "utr_number", "VARCHAR(100)")
    _add_column_if_missing("bookings", "payment_screenshot", "VARCHAR(255)")
    
    _add_column_if_missing("trips", "feedback_rating", "INTEGER")
    _add_column_if_missing("trips", "feedback_text", "TEXT")
    
    # Add updated_at to all tables using TimestampMixin
    all_tables = [
        "users", "clients", "agent_travelers", "trips", "destinations", 
        "itineraries", "hotels", "bookings", "payments", "activities",
        "itinerary_edit_requests", "notification_logs", "trip_update_requests"
    ]
    for table in all_tables:
        _add_column_if_missing(table, "updated_at", "DATETIME DEFAULT '2026-01-01 00:00:00'")
    
    db.session.commit()
