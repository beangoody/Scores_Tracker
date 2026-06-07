"""app/sports.py
Sports blueprint for Trackr.

Exposes the sports table as a JSON API so the log-match form
can fetch the scoring rules for whichever sport the user selects
and validate scores client-side before submitting.

Routes:
    GET /sports/api/all         — list all sports
    GET /sports/api/<sport_id>  — single sport rules
"""

from flask import Blueprint, jsonify, abort
from flask_login import login_required

from app.models import db, Sport

sports_bp = Blueprint("sports", __name__, url_prefix="/sports")


@sports_bp.route("/api/all")
@login_required
def get_all_sports():
    """Return all sports as a JSON array.

    Used by the log-match form to populate the sport picker dropdown
    and load the correct scoring rules into the JS validator.

    Returns:
        200 — [{ id, name, scoring_type, target_score,
                 win_by_two, score_cap, match_winner_rule,
                 allows_draw }, ...]
    """
    sports = Sport.query.order_by(Sport.name).all()
    return jsonify([s.to_dict() for s in sports])


@sports_bp.route("/api/<int:sport_id>")
@login_required
def get_sport(sport_id: int):
    """Return the rules for a single sport.

    Used by the JS validator on the log-match form to check each
    game score as the user types it.

    Args:
        sport_id: Primary key of the sport.

    Returns:
        200 — { id, name, scoring_type, target_score,
                win_by_two, score_cap, match_winner_rule, allows_draw }
        404 — if sport_id does not exist
    """
    sport = db.session.get(Sport, sport_id)
    if sport is None:
        abort(404, description=f"Sport {sport_id} not found.")
    return jsonify(sport.to_dict())