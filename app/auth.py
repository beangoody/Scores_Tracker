"""app/auth.py
Authentication blueprint for Trackr.

Routes:
    GET  /auth/register  — show registration form
    POST /auth/register  — create account
    GET  /auth/login     — show login form
    POST /auth/login     — validate credentials and set session
    GET  /auth/logout    — clear session and redirect
"""

from flask import (
    Blueprint, render_template, redirect,
    url_for, flash, request, session
)
from flask_login import login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

from app.models import db, User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
bcrypt  = Bcrypt()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_password(plaintext: str) -> str:
    return bcrypt.generate_password_hash(plaintext).decode("utf-8")


def _check_password(plaintext: str, hashed: str) -> bool:
    return bcrypt.check_password_hash(hashed, plaintext)


def _validate_registration(username: str, email: str, password: str) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    if not username or len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if len(username) > 40:
        errors.append("Username must be 40 characters or fewer.")
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if User.query.filter_by(username=username).first():
        errors.append("That username is already taken.")
    if User.query.filter_by(email=email).first():
        errors.append("An account with that email already exists.")
    return errors


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("matches.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email",    "").strip().lower()
        password = request.form.get("password", "")

        errors = _validate_registration(username, email, password)
        if errors:
            for error in errors:
                flash(error, "error")
            # Re-render form with the values they typed so they don't
            # have to retype everything
            return render_template(
                "auth/register.html",
                username=username,
                email=email,
            )

        user = User(
            username      = username,
            email         = email,
            password_hash = _hash_password(password),
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(f"Welcome to Trackr, {username}!", "success")
        return redirect(url_for("matches.dashboard"))

    return render_template("auth/register.html", username="", email="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("matches.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()

        if not user or not _check_password(password, user.password_hash):
            flash("Incorrect username or password.", "error")
            return render_template("auth/login.html", username=username)

        login_user(user, remember=remember)
        flash(f"Welcome back, {user.username}!", "success")

        # Respect the ?next= redirect that Flask-Login sets
        next_page = request.args.get("next")
        return redirect(next_page or url_for("matches.dashboard"))

    return render_template("auth/login.html", username="")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))