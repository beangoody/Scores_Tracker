"""app/social.py
Social blueprint for Trackr.

Routes:
    GET  /social/players                  — search + friend recommendations
    POST /social/friend/<user_id>         — send a friend request
    POST /social/friend/accept/<req_id>   — accept a friend request
    POST /social/friend/decline/<req_id>  — decline a friend request
    POST /social/friend/remove/<user_id>  — remove an existing friend
    GET  /social/leaderboard              — ranked table, optional ?sport_id=
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.models import db, User, FriendRequest, Sport
from app.stats  import get_win_rate

social_bp   = Blueprint("social", __name__, url_prefix="/social")
MIN_MATCHES = 3   # minimum confirmed matches to appear on leaderboard


# ── Friend helpers ────────────────────────────────────────────────────────────

def get_friends(user_id: int) -> list[User]:
    """Return all users with an accepted friend request with user_id."""
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
    friend_ids = {
        req.to_user_id if req.from_user_id == user_id else req.from_user_id
        for req in accepted
    }
    return User.query.filter(User.id.in_(friend_ids)).order_by(User.username).all()


def get_friend_ids(user_id: int) -> set[int]:
    return {u.id for u in get_friends(user_id)}


def get_pending_received(user_id: int) -> list[FriendRequest]:
    return FriendRequest.query.filter_by(to_user_id=user_id, status="pending").all()


def _already_friends(user_a: int, user_b: int) -> bool:
    return FriendRequest.query.filter(
        or_(
            (FriendRequest.from_user_id == user_a) & (FriendRequest.to_user_id == user_b),
            (FriendRequest.from_user_id == user_b) & (FriendRequest.to_user_id == user_a),
        ),
        FriendRequest.status == "accepted",
    ).first() is not None


def _pending_exists(user_a: int, user_b: int) -> bool:
    return FriendRequest.query.filter(
        or_(
            (FriendRequest.from_user_id == user_a) & (FriendRequest.to_user_id == user_b),
            (FriendRequest.from_user_id == user_b) & (FriendRequest.to_user_id == user_a),
        ),
        FriendRequest.status == "pending",
    ).first() is not None


def get_friend_recommendations(user_id: int, limit: int = 8) -> list[dict]:
    """Return suggested players to add as friends.

    Priority order:
      1. Friends-of-friends (people your friends know, sorted by how many
         mutual friends you share)
      2. Most active players overall (most confirmed matches), excluding
         people already known

    People already friended, with a pending request, or who are the
    current user are always excluded.
    """
    my_friend_ids = get_friend_ids(user_id)
    already_known = my_friend_ids | {user_id}

    # ── Friends of friends ────────────────────────────────────────────────────
    mutual_counts: dict[int, int] = {}
    for fid in my_friend_ids:
        for fof in get_friend_ids(fid):
            if fof in already_known:
                continue
            if _pending_exists(user_id, fof):
                continue
            mutual_counts[fof] = mutual_counts.get(fof, 0) + 1

    # Sort by mutual friend count descending
    fof_ids = sorted(mutual_counts, key=lambda x: mutual_counts[x], reverse=True)

    recommendations: list[dict] = []
    for uid2 in fof_ids[:limit]:
        user = db.session.get(User, uid2)
        if user:
            recommendations.append({
                "user":    user,
                "reason":  f"{mutual_counts[uid2]} mutual friend{'s' if mutual_counts[uid2] != 1 else ''}",
                "mutuals": mutual_counts[uid2],
            })

    # ── Fill remaining slots with most-active players ─────────────────────────
    if len(recommendations) < limit:
        from app.models import Match
        from sqlalchemy import func

        # Count confirmed matches per player
        match_counts = (
            db.session.query(
                Match.player1_id.label("uid"),
                func.count(Match.id).label("cnt"),
            )
            .filter(Match.confirmed == True)
            .group_by(Match.player1_id)
            .union_all(
                db.session.query(
                    Match.player2_id.label("uid"),
                    func.count(Match.id).label("cnt"),
                )
                .filter(Match.confirmed == True)
                .group_by(Match.player2_id)
            )
            .subquery()
        )

        already_rec_ids = {r["user"].id for r in recommendations} | already_known
        pending_sent    = {
            req.to_user_id
            for req in FriendRequest.query.filter_by(
                from_user_id=user_id, status="pending"
            ).all()
        }
        exclude = already_rec_ids | pending_sent

        active_users = (
            db.session.query(
                User,
                func.sum(match_counts.c.cnt).label("total"),
            )
            .join(match_counts, User.id == match_counts.c.uid)
            .filter(User.id.notin_(exclude))
            .group_by(User.id)
            .order_by(func.sum(match_counts.c.cnt).desc())
            .limit(limit - len(recommendations))
            .all()
        )

        for user, total in active_users:
            recommendations.append({
                "user":    user,
                "reason":  f"{total} match{'es' if total != 1 else ''} played",
                "mutuals": 0,
            })

    return recommendations[:limit]


# ── Routes ────────────────────────────────────────────────────────────────────

@social_bp.route("/players")
@login_required
def search_players():
    """Player search + friend recommendations + pending requests."""
    query   = request.args.get("q", "").strip()
    results = []

    if query:
        raw = (
            User.query
            .filter(
                User.username.ilike(f"%{query}%"),
                User.id != current_user.id,
            )
            .order_by(User.username)
            .limit(20)
            .all()
        )
        for user in raw:
            if _already_friends(current_user.id, user.id):
                status = "friends"
            elif _pending_exists(current_user.id, user.id):
                status = "pending"
            else:
                status = "none"
            results.append({"user": user, "status": status})

    friends         = get_friends(current_user.id)
    pending_in      = get_pending_received(current_user.id)
    recommendations = get_friend_recommendations(current_user.id) if not query else []

    return render_template(
        "players.html",
        query           = query,
        results         = results,
        friends         = friends,
        pending         = pending_in,
        recommendations = recommendations,
    )


@social_bp.route("/friend/<int:user_id>", methods=["POST"])
@login_required
def send_friend_request(user_id: int):
    if user_id == current_user.id:
        flash("You cannot add yourself.", "error")
        return redirect(url_for("social.search_players"))

    target = db.session.get(User, user_id)
    if target is None:
        abort(404)

    if _already_friends(current_user.id, user_id):
        flash(f"You are already friends with {target.username}.", "info")
        return redirect(request.referrer or url_for("social.search_players"))

    if _pending_exists(current_user.id, user_id):
        flash(f"A request with {target.username} is already pending.", "info")
        return redirect(request.referrer or url_for("social.search_players"))

    db.session.add(FriendRequest(from_user_id=current_user.id, to_user_id=user_id))
    db.session.commit()
    flash(f"Friend request sent to {target.username}!", "success")
    return redirect(request.referrer or url_for("social.search_players"))


@social_bp.route("/friend/accept/<int:req_id>", methods=["POST"])
@login_required
def accept_friend_request(req_id: int):
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
    req = db.session.get(FriendRequest, req_id)
    if req is None or req.to_user_id != current_user.id:
        abort(403)
    req.decline()
    db.session.commit()
    flash("Friend request declined.", "info")
    return redirect(url_for("social.search_players"))


@social_bp.route("/friend/remove/<int:user_id>", methods=["POST"], endpoint="remove_friend")
@login_required
def remove_friend(user_id: int):  # noqa
    """Remove an existing friendship (either direction)."""
    req = FriendRequest.query.filter(
        or_(
            (FriendRequest.from_user_id == current_user.id) & (FriendRequest.to_user_id == user_id),
            (FriendRequest.from_user_id == user_id) & (FriendRequest.to_user_id == current_user.id),
        ),
        FriendRequest.status == "accepted",
    ).first()

    if req is None:
        flash("You are not friends with that player.", "error")
        return redirect(url_for("social.search_players"))

    user = db.session.get(User, user_id)
    db.session.delete(req)
    db.session.commit()
    flash(f"Removed {user.username} from your friends.", "info")
    return redirect(url_for("social.search_players"))


@social_bp.route("/leaderboard")
@login_required
def leaderboard():
    sport_id = request.args.get("sport_id", type=int)
    sport    = db.session.get(Sport, sport_id) if sport_id else None
    sports   = Sport.query.order_by(Sport.name).all()
    friends  = get_friends(current_user.id)
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

    rankings.sort(key=lambda x: (x["rate"], x["total"]), reverse=True)
    for i, entry in enumerate(rankings, start=1):
        entry["rank"] = i

    return render_template(
        "leaderboard.html",
        rankings    = rankings,
        sport       = sport,
        sports      = sports,
        min_matches = MIN_MATCHES,
    )