"""app/stats.py
Statistics blueprint for Trackr.

All stat functions only count *confirmed* matches so disputed or
pending results never pollute the numbers.

Routes:
    GET /stats/profile                — your own stats page
    GET /stats/profile/<user_id>      — another player's public profile
    GET /stats/h2h/<user_id>          — head-to-head vs one opponent
    GET /stats/api/form               — JSON: last n results for Chart.js
                                        optional ?sport_id=<id>&n=<int>
"""

from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.models import db, Match, Sport, User

stats_bp = Blueprint("stats", __name__, url_prefix="/stats")


# ── Core stat helpers ─────────────────────────────────────────────────────────

def get_confirmed_matches(user_id: int, sport_id: int | None = None):
    """Return all confirmed matches for a user, newest first.

    Args:
        user_id:  The user to query for.
        sport_id: Optional — filter to one sport.

    Returns:
        List of Match objects.
    """
    q = (
        Match.query
        .filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.confirmed == True,
        )
        .order_by(Match.played_at.desc())
    )
    if sport_id is not None:
        q = q.filter(Match.sport_id == sport_id)
    return q.all()


def get_win_rate(
    user_id: int,
    sport_id: int | None = None,
    opponent_id: int | None = None,
) -> dict:
    """Calculate win / loss / draw counts and win percentage.

    Args:
        user_id:     The player to calculate stats for.
        sport_id:    Optional — filter to one sport.
        opponent_id: Optional — filter to H2H vs one opponent.

    Returns:
        {
            wins:   int,
            losses: int,
            draws:  int,
            total:  int,
            rate:   float,   # 0.0 – 1.0, excludes draws from denominator
        }
    """
    q = (
        Match.query
        .filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.confirmed == True,
        )
    )
    if sport_id is not None:
        q = q.filter(Match.sport_id == sport_id)
    if opponent_id is not None:
        q = q.filter(
            or_(
                Match.player1_id == opponent_id,
                Match.player2_id == opponent_id,
            )
        )

    matches = q.all()

    wins = losses = draws = 0
    for m in matches:
        if m.winner_id is None:
            draws += 1
        elif m.winner_id == user_id:
            wins += 1
        else:
            losses += 1

    decisive = wins + losses  # draws excluded from rate denominator
    rate = (wins / decisive) if decisive > 0 else 0.0

    return {
        "wins":   wins,
        "losses": losses,
        "draws":  draws,
        "total":  len(matches),
        "rate":   round(rate, 3),
    }


def get_current_streak(user_id: int, sport_id: int | None = None) -> dict:
    """Return the current unbroken win or loss streak.

    Args:
        user_id:  The player to check.
        sport_id: Optional — filter to one sport.

    Returns:
        { type: "W" | "L" | "D" | None, length: int }
        type is None when no confirmed matches exist.
    """
    matches = get_confirmed_matches(user_id, sport_id)

    if not matches:
        return {"type": None, "length": 0}

    # Determine result of the most recent match to set the streak type
    first = matches[0]
    if first.winner_id is None:
        streak_type = "D"
    elif first.winner_id == user_id:
        streak_type = "W"
    else:
        streak_type = "L"

    length = 0
    for m in matches:
        if m.winner_id is None:
            result = "D"
        elif m.winner_id == user_id:
            result = "W"
        else:
            result = "L"

        if result == streak_type:
            length += 1
        else:
            break  # streak broken

    return {"type": streak_type, "length": length}


def get_sport_breakdown(user_id: int) -> list[dict]:
    """Win rate broken down per sport.

    Only includes sports where the user has played at least one
    confirmed match.

    Returns:
        [
            { sport_id, sport_name, wins, losses, draws, total, rate },
            ...
        ]
        Sorted by total matches descending (most played sport first).
    """
    sports = Sport.query.all()
    breakdown = []

    for sport in sports:
        stats = get_win_rate(user_id, sport_id=sport.id)
        if stats["total"] == 0:
            continue
        breakdown.append({
            "sport_id":   sport.id,
            "sport_name": sport.name,
            **stats,
        })

    breakdown.sort(key=lambda x: x["total"], reverse=True)
    return breakdown


def get_form(
    user_id: int,
    sport_id: int | None = None,
    n: int = 10,
) -> list[dict]:
    """Last n match results — used to feed the Chart.js form chart.

    Args:
        user_id:  The player to query.
        sport_id: Optional sport filter.
        n:        How many recent matches to return (default 10).

    Returns:
        [
            { date: "YYYY-MM-DD", result: "W"|"L"|"D", sport: str },
            ...
        ]
        Ordered oldest → newest so Chart.js plots left to right.
    """
    matches = get_confirmed_matches(user_id, sport_id)[:n]

    form = []
    for m in reversed(matches):   # oldest first for charting
        if m.winner_id is None:
            result = "D"
        elif m.winner_id == user_id:
            result = "W"
        else:
            result = "L"

        form.append({
            "date":   m.played_at.strftime("%Y-%m-%d"),
            "result": result,
            "sport":  m.sport.name,
        })

    return form


def get_game_stats(user_id: int, sport_id: int | None = None) -> dict:
    """Average points scored and conceded per game.

    Args:
        user_id:  The player to query.
        sport_id: Optional sport filter.

    Returns:
        {
            avg_scored:    float,
            avg_conceded:  float,
            game_win_pct:  float,   # % of individual games won
            games_played:  int,
        }
    """
    matches = get_confirmed_matches(user_id, sport_id)

    scored = conceded = games_won = games_played = 0

    for m in matches:
        is_p1 = (m.player1_id == user_id)
        for g in m.games:
            if g.score_p1 is None or g.score_p2 is None:
                continue
            my_score  = g.score_p1 if is_p1 else g.score_p2
            opp_score = g.score_p2 if is_p1 else g.score_p1
            scored    += my_score
            conceded  += opp_score
            games_played += 1
            if my_score > opp_score:
                games_won += 1

    if games_played == 0:
        return {
            "avg_scored":   0.0,
            "avg_conceded": 0.0,
            "game_win_pct": 0.0,
            "games_played": 0,
        }

    return {
        "avg_scored":   round(scored   / games_played, 1),
        "avg_conceded": round(conceded / games_played, 1),
        "game_win_pct": round(games_won / games_played, 3),
        "games_played": games_played,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@stats_bp.route("/profile")
@login_required
def profile():
    """Your own stats page — per-sport tabs + overall summary."""
    uid       = current_user.id
    overall   = get_win_rate(uid)
    streak    = get_current_streak(uid)
    breakdown = get_sport_breakdown(uid)
    game_stats = get_game_stats(uid)

    return render_template(
        "profile.html",
        player    = current_user,
        overall   = overall,
        streak    = streak,
        breakdown = breakdown,
        game_stats = game_stats,
        own_profile = True,
    )


@stats_bp.route("/profile/<int:user_id>")
@login_required
def public_profile(user_id: int):
    """Another player's public profile."""
    if user_id == current_user.id:
        return profile()   # redirect to own profile logic

    player = db.session.get(User, user_id)
    if player is None:
        abort(404)

    overall    = get_win_rate(user_id)
    streak     = get_current_streak(user_id)
    breakdown  = get_sport_breakdown(user_id)
    game_stats = get_game_stats(user_id)

    return render_template(
        "profile.html",
        player     = player,
        overall    = overall,
        streak     = streak,
        breakdown  = breakdown,
        game_stats = game_stats,
        own_profile = False,
    )


@stats_bp.route("/h2h/<int:opponent_id>")
@login_required
def head_to_head(opponent_id: int):
    """Head-to-head stats vs a specific opponent.

    Optional query param: ?sport_id=<int> to filter to one sport.
    """
    opponent = db.session.get(User, opponent_id)
    if opponent is None:
        abort(404)

    sport_id = request.args.get("sport_id", type=int)
    sport    = db.session.get(Sport, sport_id) if sport_id else None

    my_stats  = get_win_rate(current_user.id, sport_id=sport_id, opponent_id=opponent_id)
    opp_stats = get_win_rate(opponent_id,     sport_id=sport_id, opponent_id=current_user.id)

    # Recent H2H matches (newest first, capped at 20)
    q = (
        Match.query
        .filter(
            or_(
                (Match.player1_id == current_user.id) & (Match.player2_id == opponent_id),
                (Match.player1_id == opponent_id)     & (Match.player2_id == current_user.id),
            ),
            Match.confirmed == True,
        )
        .order_by(Match.played_at.desc())
        .limit(20)
    )
    if sport_id:
        q = q.filter(Match.sport_id == sport_id)
    recent = q.all()

    return render_template(
        "head_to_head.html",
        opponent  = opponent,
        my_stats  = my_stats,
        opp_stats = opp_stats,
        recent    = recent,
        sport     = sport,
        sports    = Sport.query.order_by(Sport.name).all(),
    )


@stats_bp.route("/api/form")
@login_required
def form_json():
    """JSON endpoint for the Chart.js form chart.

    Query params:
        sport_id (int, optional) — filter to one sport
        n        (int, optional) — number of results, default 10, max 50

    Returns:
        200 — { labels: [...], results: [...], sports: [...] }
    """
    sport_id = request.args.get("sport_id", type=int)
    n        = min(request.args.get("n", default=10, type=int), 50)

    form = get_form(current_user.id, sport_id=sport_id, n=n)

    return jsonify({
        "labels":  [entry["date"]   for entry in form],
        "results": [entry["result"] for entry in form],
        "sports":  [entry["sport"]  for entry in form],
    })