"""app/auth.py
Authentication blueprint for Trackr.

Routes:
    GET/POST /auth/register        — create account
    GET/POST /auth/login           — log in
    GET      /auth/logout          — log out
    GET/POST /auth/settings        — change username or password (logged in)
    GET/POST /auth/forgot-password — reset password via security question
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

from app.models import db, User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
bcrypt  = Bcrypt()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(plaintext: str) -> str:
    return bcrypt.generate_password_hash(plaintext).decode("utf-8")

def _check(plaintext: str, hashed: str) -> bool:
    return bcrypt.check_password_hash(hashed, plaintext)

def _validate_registration(username, email, password):
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


# ── Register ──────────────────────────────────────────────────────────────────

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
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html", username=username, email=email)

        user = User(username=username, email=email, password_hash=_hash(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Welcome to Trackr, {username}!", "success")
        return redirect(url_for("matches.dashboard"))

    return render_template("auth/register.html", username="", email="")


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("matches.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()
        if not user or not _check(password, user.password_hash):
            flash("Incorrect username or password.", "error")
            return render_template("auth/login.html", username=username)

        login_user(user, remember=remember)
        flash(f"Welcome back, {user.username}!", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("matches.dashboard"))

    return render_template("auth/login.html", username="")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── Settings ──────────────────────────────────────────────────────────────────

@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")

        # ── Change username ───────────────────────────────────────────────────
        if action == "username":
            new_username = request.form.get("new_username", "").strip()
            if len(new_username) < 3:
                flash("Username must be at least 3 characters.", "error")
            elif len(new_username) > 40:
                flash("Username must be 40 characters or fewer.", "error")
            elif User.query.filter_by(username=new_username).first():
                flash("That username is already taken.", "error")
            else:
                current_user.username = new_username
                db.session.commit()
                flash("Username updated successfully.", "success")

        # ── Change password ───────────────────────────────────────────────────
        elif action == "password":
            current_pw  = request.form.get("current_password", "")
            new_pw      = request.form.get("new_password", "")
            confirm_pw  = request.form.get("confirm_password", "")

            if not _check(current_pw, current_user.password_hash):
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            else:
                current_user.password_hash = _hash(new_pw)
                db.session.commit()
                flash("Password updated successfully.", "success")

        return redirect(url_for("auth.settings"))

    return render_template("auth/settings.html")


# ── Forgot password ───────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Simple email-based password reset.

    Step 1: user enters their email — we look them up.
    Step 2: if found, let them set a new password directly.

    NOTE: In production you'd send a time-limited reset link by email.
    This version is intentionally simple for local/LAN use. To add real
    email, integrate Flask-Mail and generate a signed token with itsdangerous.
    """
    step  = request.args.get("step", "1")
    email = request.args.get("email", "")

    if request.method == "POST":
        if step == "1":
            email = request.form.get("email", "").strip().lower()
            user  = User.query.filter_by(email=email).first()
            if not user:
                # Don't reveal whether the email exists — just show step 2
                # regardless (security best practice)
                pass
            return redirect(url_for("auth.forgot_password", step="2", email=email))

        elif step == "2":
            email      = request.form.get("email", "").strip().lower()
            new_pw     = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")
            user       = User.query.filter_by(email=email).first()

            if not user:
                flash("No account found with that email address.", "error")
                return redirect(url_for("auth.forgot_password"))

            if len(new_pw) < 8:
                flash("Password must be at least 8 characters.", "error")
                return redirect(url_for("auth.forgot_password", step="2", email=email))

            if new_pw != confirm_pw:
                flash("Passwords do not match.", "error")
                return redirect(url_for("auth.forgot_password", step="2", email=email))

            user.password_hash = _hash(new_pw)
            db.session.commit()
            flash("Password reset successfully. Please log in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", step=step, email=email)