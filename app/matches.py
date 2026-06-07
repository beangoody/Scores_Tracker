"""app/matches.py
Matches blueprint for Trackr.

Routes:
    GET  /          — dashboard (recent matches, quick stats)
    GET  /log       — log match form
    POST /log       — submit a new match
    GET  /match/<id>         — detail view for one match
    POST /match/<id>/confirm — opponent confirms the result
    POST /match/<id>/dispute — opponent flags a disputed result
"""

from datetime import datetime

from flask import (
    Blueprint, render_template, redirect,
    url_for, flash, request, abort
)
from flask_login import login_required, current_user

from app.models import db, Match, Game, Sport, User
from app.utils  import validate_game_score, infer_match_winner, ValidationError

matches_bp = Blueprint("matches", __name__)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@matches_bp.route("/")
@login_required
def dashboard():
    """Home page — 10 most recent confirmed + pending matches for the user."""
    uid = current_user.id
    recent = (
        Match.query
        .filter(
            (Match.player1_id == uid) | (Match.player2_id == uid)
        )
        .order_by(Match.played_at.desc())
        .limit(10)
        .all()
    )
    return render_template("dashboard.html", matches=recent)


# ── Log a match ───────────────────────────────────────────────────────────────

@matches_bp.route("/log", methods=["GET", "POST"])
@login_required
def log_match():
    sports = Sport.query.order_by(Sport.name).all()

    if request.method == "GET":
        users = (
            User.query
            .filter(User.id != current_user.id)
            .order_by(User.username)
            .all()
        )
        return render_template("log_match.html", sports=sports, users=users)

    # ── POST — parse and save the match ──────────────────────────────────────
    sport_id   = request.form.get("sport_id",   type=int)
    opponent_id = request.form.get("opponent_id", type=int)
    location   = request.form.get("location", "").strip() or None

    sport    = db.session.get(Sport, sport_id)
    opponent = db.session.get(User,  opponent_id)

    if not sport or not opponent:
        flash("Invalid sport or opponent.", "error")
        return redirect(url_for("matches.log_match"))

    if opponent.id == current_user.id:
        flash("You cannot log a match against yourself.", "error")
        return redirect(url_for("matches.log_match"))

    # ── Result-only sport (chess) ─────────────────────────────────────────────
    if sport.scoring_type == "result":
        result = request.form.get("result")
        if result not in ("win", "loss", "draw"):
            flash("Please select a valid result (win / loss / draw).", "error")
            return redirect(url_for("matches.log_match"))

        if result == "win":
            winner_id = current_user.id
        elif result == "loss":
            winner_id = opponent.id
        else:
            winner_id = None  # draw

        match = Match(
            sport_id   = sport.id,
            player1_id = current_user.id,
            player2_id = opponent.id,
            winner_id  = winner_id,
            result     = result,
            location   = location,
        )
        db.session.add(match)
        db.session.commit()
        flash("Match logged! Waiting for your opponent to confirm.", "success")
        return redirect(url_for("matches.match_detail", match_id=match.id))

    # ── Numeric sport — parse game scores ────────────────────────────────────
    # The form posts scores as: score_p1_1, score_p2_1, score_p1_2, … etc.
    games_raw = []
    game_num  = 1
    while True:
        s1 = request.form.get(f"score_p1_{game_num}", type=int)
        s2 = request.form.get(f"score_p2_{game_num}", type=int)
        if s1 is None and s2 is None:
            break  # No more game rows submitted
        if s1 is None or s2 is None:
            flash(f"Both scores are required for game {game_num}.", "error")
            return redirect(url_for("matches.log_match"))
        games_raw.append((s1, s2, game_num))
        game_num += 1

    if not games_raw:
        flash("Please enter scores for at least one game.", "error")
        return redirect(url_for("matches.log_match"))

    # Validate each game score against the sport's rules
    try:
        for s1, s2, num in games_raw:
            validate_game_score(sport, s1, s2)
    except ValidationError as exc:
        flash(f"Game {num}: {exc}", "error")
        return redirect(url_for("matches.log_match"))

    # Infer overall winner
    try:
        winner_id = infer_match_winner(
            sport,
            current_user.id,
            opponent.id,
            [(s1, s2) for s1, s2, _ in games_raw],
        )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("matches.log_match"))

    # Persist match + game rows
    match = Match(
        sport_id   = sport.id,
        player1_id = current_user.id,
        player2_id = opponent.id,
        winner_id  = winner_id,
        location   = location,
    )
    db.session.add(match)
    db.session.flush()  # Get match.id before committing

    for s1, s2, num in games_raw:
        db.session.add(Game(
            match_id    = match.id,
            game_number = num,
            score_p1    = s1,
            score_p2    = s2,
        ))

    db.session.commit()
    flash("Match logged! Waiting for your opponent to confirm.", "success")
    return redirect(url_for("matches.match_detail", match_id=match.id))


# ── Match detail ──────────────────────────────────────────────────────────────

@matches_bp.route("/match/<int:match_id>")
@login_required
def match_detail(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    # Only the two players can view an unconfirmed match
    if current_user.id not in (match.player1_id, match.player2_id):
        abort(403)
    return render_template("match_detail.html", match=match)


# ── Confirm ───────────────────────────────────────────────────────────────────

@matches_bp.route("/match/<int:match_id>/confirm", methods=["POST"])
@login_required
def confirm_match(match_id: int):
    """Opponent confirms the match result is correct."""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    # Only the opponent (player2) can confirm — the logger (player1)
    # already agreed to the result by submitting it
    if current_user.id != match.player2_id:
        flash("Only the opponent can confirm a match result.", "error")
        return redirect(url_for("matches.match_detail", match_id=match_id))

    if match.confirmed:
        flash("This match has already been confirmed.", "info")
        return redirect(url_for("matches.match_detail", match_id=match_id))

    match.confirm()
    db.session.commit()
    flash("Match confirmed! Stats have been updated.", "success")
    return redirect(url_for("matches.match_detail", match_id=match_id))


# ── Dispute ───────────────────────────────────────────────────────────────────

@matches_bp.route("/match/<int:match_id>/dispute", methods=["POST"])
@login_required
def dispute_match(match_id: int):
    """Opponent flags the result as incorrect."""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    if current_user.id != match.player2_id:
        flash("Only the opponent can dispute a match result.", "error")
        return redirect(url_for("matches.match_detail", match_id=match_id))

    if match.confirmed:
        flash("A confirmed match cannot be disputed.", "error")
        return redirect(url_for("matches.match_detail", match_id=match_id))

    # For now, disputing deletes the match so both players can re-log it.
    # A future version could flag it for admin review instead.
    db.session.delete(match)
    db.session.commit()
    flash(
        "Match disputed and removed. "
        "Please re-log the result together with your opponent.",
        "warning"
    )
    return redirect(url_for("matches.dashboard"))