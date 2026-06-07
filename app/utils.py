"""app/utils.py
Shared helpers for Trackr.

Key functions:
    validate_game_score(sport, score_p1, score_p2)
        Checks a single game score obeys the sport's rules.

    infer_match_winner(sport, player1_id, player2_id, games)
        Given a list of (score_p1, score_p2) tuples, returns the
        winner's user id or None for a draw.

    login_required is re-exported from flask_login for convenience.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Sport


class ValidationError(Exception):
    """Raised when a score or match submission violates sport rules."""
    pass


# ── Score validation ──────────────────────────────────────────────────────────

def validate_game_score(sport: "Sport", score_p1: int, score_p2: int) -> bool:
    """Validate a single game score against a sport's rules.

    Checks performed:
        1. Both scores are non-negative integers.
        2. At least one player has reached the target score.
        3. If win_by_two is True, the winner leads by at least 2.
        4. Neither score exceeds score_cap (if one is set).

    Args:
        sport:    The Sport model instance containing the rules.
        score_p1: Score for player 1.
        score_p2: Score for player 2.

    Returns:
        True if the score is valid.

    Raises:
        ValidationError: With a human-readable message describing the problem.

    Examples:
        Squash (target=11, win_by_two=True, score_cap=None):
            11-9  → valid
            11-10 → invalid (not won by 2)
            12-10 → valid
            14-13 → invalid (not won by 2)
            14-12 → valid
    """
    if not isinstance(score_p1, int) or not isinstance(score_p2, int):
        raise ValidationError("Scores must be whole numbers.")
    if score_p1 < 0 or score_p2 < 0:
        raise ValidationError("Scores cannot be negative.")

    high  = max(score_p1, score_p2)
    low   = min(score_p1, score_p2)
    target = sport.target_score

    # ── Score cap ────────────────────────────────────────────────────────────
    if sport.score_cap is not None and high > sport.score_cap:
        raise ValidationError(
            f"Score {high} exceeds the maximum allowed score of "
            f"{sport.score_cap} for {sport.name}."
        )

    # ── Result-only sports (chess) ───────────────────────────────────────────
    if sport.scoring_type == "result":
        # No numeric scores expected — caller should not be calling this
        raise ValidationError(
            f"{sport.name} does not use numeric game scores. "
            "Log a result (win/loss/draw) instead."
        )

    # ── Target score must be reached ─────────────────────────────────────────
    if target is not None and high < target:
        raise ValidationError(
            f"Neither player has reached the target score of "
            f"{target} for {sport.name}. "
            f"Got {score_p1}-{score_p2}."
        )

    # ── Win by two ───────────────────────────────────────────────────────────
    if sport.win_by_two:
        if high - low < 2:
            raise ValidationError(
                f"{sport.name} requires winning by at least 2 points. "
                f"Got {score_p1}-{score_p2}."
            )

        # If both are at or above target the margin must be exactly 2
        # (e.g. squash: 13-12 is valid but 14-12 is only valid if target
        # was already passed — 14-11 is also valid)
        if target is not None and low >= target and high - low != 2:
            raise ValidationError(
                f"Once both players pass {target}, the game must be "
                f"decided by exactly 2 points. Got {score_p1}-{score_p2}."
            )

    return True


# ── Match winner inference ────────────────────────────────────────────────────

def infer_match_winner(
    sport,
    player1_id: int,
    player2_id: int,
    games: list[tuple[int, int]],
) -> int | None:
    """Determine the match winner from the game scores.

    Works for any number of games — does not enforce a best-of limit,
    because the number of games played varies day to day.

    Args:
        sport:      The Sport model instance.
        player1_id: User ID of player 1.
        player2_id: User ID of player 2.
        games:      List of (score_p1, score_p2) tuples, one per game.

    Returns:
        player1_id if player 1 won more games,
        player2_id if player 2 won more games,
        None       if equal (draw — only valid for sports that allow draws).

    Raises:
        ValidationError: If the result is a draw on a sport that doesn't
                         allow draws.
    """
    p1_games = sum(1 for s1, s2 in games if s1 > s2)
    p2_games = sum(1 for s1, s2 in games if s2 > s1)

    if p1_games > p2_games:
        return player1_id
    if p2_games > p1_games:
        return player2_id

    # Equal games won — draw
    if sport.allows_draw:
        return None
    raise ValidationError(
        f"{sport.name} does not allow draws but the game scores are equal "
        f"({p1_games}-{p2_games}). Check the scores and try again."
    )