import os
from datetime import datetime, timedelta

from flask import Flask
from sqlalchemy import event

from app.config import Config
from app.controllers.agent_controller import agent_bp
from app.controllers.auth_controller import auth_bp
from app.controllers.main_controller import main_bp
from app.controllers.traveler_controller import traveler_bp
from app.extensions import db, login_manager
from app.models import (  # noqa: F401
    AgentTraveler,
    Activity,
    Booking,
    Client,
    Destination,
    Hotel,
    ItineraryEditRequest,
    Itinerary,
    NotificationLog,
    Payment,
    Trip,
    TripUpdateRequest,
    User,
)
from app.services.schema_service import ensure_sqlite_schema_updates
from app.services.seed_service import seed_hotels


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    app.jinja_env.globals.update(datetime=datetime, timedelta=timedelta)
    os.makedirs(app.config.get("INSTANCE_DIR", app.instance_path), exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_sqlite_schema_updates()

    if app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("sqlite"):
        if not getattr(create_app, "_sqlite_pragmas_registered", False):
            from sqlite3 import Connection as SQLite3Connection

            with app.app_context():
                engine = db.engine

            @event.listens_for(engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _connection_record):
                if isinstance(dbapi_connection, SQLite3Connection):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA synchronous=NORMAL;")
                    cursor.execute("PRAGMA busy_timeout=60000;")
                    cursor.close()

            create_app._sqlite_pragmas_registered = True

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(traveler_bp, url_prefix="/traveler")
    app.register_blueprint(agent_bp, url_prefix="/agent")

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables and seed starter data."""
        db.create_all()
        seed_hotels()
        print("Database initialized.")

    return app
