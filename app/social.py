"""app/social.py
Social blueprint for Trackr.

Handles friend requests, player search, and the leaderboard.
The leaderboard only ranks players who are mutual friends and
have at least MIN_MATCHES confirmed matches.

Routes:
    GET  /social/players                  — search registered players
    POST /social/friend/<user_id>         — send a friend request
    POST /social/friend/accept/<req_id>   — accept a friend request
    POST /social/friend/decline/<req_id>  — decline a friend request
    GET  /social/leaderboard              — ranked table, optional ?sport_id=
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.models import db, User, FriendRequest, Sport
from app.stats  import get_win_rate

social_bp = Blueprint("social", __name__, url_prefix="/social")

# Minimum confirmed matches to appear on the leaderboard
MIN_MATCHES = 3


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_friends(user_id: int) -> list[User]:
    """Return all users who have an accepted friend request with user_id."""
    accepted = (
        FriendRequest.query
        .filter(
            or_(
                FriendRequest.from_user_id == user_id,
                FriendRequest.to_user_id   == user_id,
            ),
            FriendRequest.status == "accepted",
        )
        .all()
    )

    friend_ids = set()
    for req in accepted:
        other = req.to_user_id if req.from_user_id == user_id else req.from_user_id
        friend_ids.add(other)

    return User.query.filter(User.id.in_(friend_ids)).order_by(User.username).all()


def get_pending_received(user_id: int) -> list[FriendRequest]:
    """Return friend requests the user has received but not yet acted on."""
    return (
        FriendRequest.query
        .filter_by(to_user_id=user_id, status="pending")
        .all()
    )


def _already_friends(user_a: int, user_b: int) -> bool:
    return FriendRequest.query.filter(
        or_(
            (FriendRequest.from_user_id == user_a) & (FriendRequest.to_user_id == user_b),
            (FriendRequest.from_user_id == user_b) & (FriendRequest.to_user_id == user_a),
        ),
        FriendRequest.status == "accepted",
    ).first() is not None


def _pending_request_exists(user_a: int, user_b: int) -> bool:
    return FriendRequest.query.filter(
        or_(
            (FriendRequest.from_user_id == user_a) & (FriendRequest.to_user_id == user_b),
            (FriendRequest.from_user_id == user_b) & (FriendRequest.to_user_id == user_a),
        ),
        FriendRequest.status == "pending",
    ).first() is not None


# ── Routes ────────────────────────────────────────────────────────────────────

@social_bp.route("/players")
@login_required
def search_players():
    """Search registered players by username.

    Query param: ?q=<search term>
    Returns players whose username contains the search term,
    excluding the current user.
    """
    query   = request.args.get("q", "").strip()
    results = []

    if query:
        results = (
            User.query
            .filter(
                User.username.ilike(f"%{query}%"),
                User.id != current_user.id,
            )
            .order_by(User.username)
            .limit(20)
            .all()
        )

    # Annotate each result with the relationship status
    annotated = []
    for user in results:
        if _already_friends(current_user.id, user.id):
            status = "friends"
        elif _pending_request_exists(current_user.id, user.id):
            status = "pending"
        else:
            status = "none"
        annotated.append({"user": user, "status": status})

    friends  = get_friends(current_user.id)
    pending  = get_pending_received(current_user.id)

    return render_template(
        "players.html",
        query     = query,
        results   = annotated,
        friends   = friends,
        pending   = pending,
    )


@social_bp.route("/friend/<int:user_id>", methods=["POST"])
@login_required
def send_friend_request(user_id: int):
    """Send a friend request to another user."""
    if user_id == current_user.id:
        flash("You cannot add yourself as a friend.", "error")
        return redirect(url_for("social.search_players"))

    target = db.session.get(User, user_id)
    if target is None:
        abort(404)

    if _already_friends(current_user.id, user_id):
        flash(f"You are already friends with {target.username}.", "info")
        return redirect(url_for("social.search_players"))

    if _pending_request_exists(current_user.id, user_id):
        flash(f"A friend request with {target.username} is already pending.", "info")
        return redirect(url_for("social.search_players"))

    req = FriendRequest(
        from_user_id = current_user.id,
        to_user_id   = user_id,
    )
    db.session.add(req)
    db.session.commit()

    flash(f"Friend request sent to {target.username}!", "success")
    return redirect(url_for("social.search_players"))


@social_bp.route("/friend/accept/<int:req_id>", methods=["POST"])
@login_required
def accept_friend_request(req_id: int):
    """Accept an incoming friend request."""
    req = db.session.get(FriendRequest, req_id)

    if req is None or req.to_user_id != current_user.id:
        abort(403)

    if req.status != "pending":
        flash("This request has already been handled.", "info")
        return redirect(url_for("social.search_players"))

    req.accept()
    db.session.commit()

    flash(f"You are now friends with {req.from_user.username}!", "success")
    return redirect(url_for("social.search_players"))


@social_bp.route("/friend/decline/<int:req_id>", methods=["POST"])
@login_required
def decline_friend_request(req_id: int):
    """Decline an incoming friend request."""
    req = db.session.get(FriendRequest, req_id)

    if req is None or req.to_user_id != current_user.id:
        abort(403)

    if req.status != "pending":
        flash("This request has already been handled.", "info")
        return redirect(url_for("social.search_players"))

    req.decline()
    db.session.commit()

    flash("Friend request declined.", "info")
    return redirect(url_for("social.search_players"))


@social_bp.route("/leaderboard")
@login_required
def leaderboard():
    """Ranked leaderboard — friends only.

    Optional query param: ?sport_id=<int> to filter to one sport.
    Players need at least MIN_MATCHES confirmed matches to appear.
    """
    sport_id = request.args.get("sport_id", type=int)
    sport    = db.session.get(Sport, sport_id) if sport_id else None
    sports   = Sport.query.order_by(Sport.name).all()

    friends  = get_friends(current_user.id)

    # Include the current user so they can see where they rank
    players  = [current_user] + friends

    rankings = []
    for player in players:
        stats = get_win_rate(player.id, sport_id=sport_id)
        if stats["total"] < MIN_MATCHES:
            continue
        rankings.append({
            "user":   player,
            "wins":   stats["wins"],
            "losses": stats["losses"],
            "draws":  stats["draws"],
            "total":  stats["total"],
            "rate":   stats["rate"],
        })

    # Sort by win rate descending, then total matches descending as tiebreaker
    rankings.sort(key=lambda x: (x["rate"], x["total"]), reverse=True)

    # Add rank numbers
    for i, entry in enumerate(rankings, start=1):
        entry["rank"] = i

    return render_template(
        "leaderboard.html",
        rankings  = rankings,
        sport     = sport,
        sports    = sports,
        min_matches = MIN_MATCHES,
    )