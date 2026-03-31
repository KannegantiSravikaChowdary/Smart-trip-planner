from flask import flash, redirect, url_for
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()

@login_manager.unauthorized_handler
def unauthorized():
    flash("Please log in to access this page.", "warning")
    return redirect(url_for("main.index"))

