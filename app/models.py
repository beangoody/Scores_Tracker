"""app/models.py
SQLAlchemy models for Trackr — a multi-sport match tracker.

Provides: `db` (Flask-SQLAlchemy instance), model classes, and `init_db(app)`.

Models:
    User          — registered player
    Sport         — sport definition + scoring rules (one row per sport)
    Match         — a single match between two players
    Game          — an individual game/set within a match
    FriendRequest — social connection between two users
"""

from datetime import datetime
from enum import Enum

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint

db = SQLAlchemy()


# ── Enums ────────────────────────────────────────────────────────────────────

class ScoringType(Enum):
    numeric = "numeric"   # games have a score (squash, tennis, badminton…)
    result  = "result"    # no score — just win/loss/draw (chess)


class FriendRequestStatus(Enum):
    pending  = "pending"
    accepted = "accepted"
    declined = "declined"


class MatchResult(Enum):
    win  = "win"
    loss = "loss"
    draw = "draw"


# ── App factory helper ────────────────────────────────────────────────────────

def init_db(app):
    """Bind the SQLAlchemy db instance to a Flask app."""
    db.init_app(app)


# ── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Flask-Login integration
    @property
    def is_active(self):      return True
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self):   return False
    def get_id(self):         return str(self.id)

    sent_requests = db.relationship(
        "FriendRequest",
        foreign_keys="FriendRequest.from_user_id",
        back_populates="from_user",
        cascade="all, delete-orphan",
    )
    received_requests = db.relationship(
        "FriendRequest",
        foreign_keys="FriendRequest.to_user_id",
        back_populates="to_user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User {self.username}>"

    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email}


class Sport(db.Model):
    """One row per sport. Adding a new sport = one INSERT, zero code changes."""
    __tablename__ = "sports"

    id                 = db.Column(db.Integer, primary_key=True)
    name               = db.Column(db.String(120), nullable=False, unique=True)
    # 'numeric' — games have scores | 'result' — win/loss/draw only (chess)
    scoring_type       = db.Column(db.String(32),  nullable=False,
                                   default=ScoringType.numeric.value)
    target_score       = db.Column(db.Integer, nullable=True)   # e.g. 11 for squash
    win_by_two         = db.Column(db.Boolean, default=False)
    score_cap          = db.Column(db.Integer, nullable=True)   # hard ceiling e.g. 30 for badminton
    # 'most_games' — whoever wins most games wins the match (squash, badminton)
    # 'sets'       — score is counted in sets (tennis, padel)
    match_winner_rule  = db.Column(db.String(32), nullable=True)
    allows_draw        = db.Column(db.Boolean, default=False)   # True for chess only

    matches = db.relationship(
        "Match", back_populates="sport", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "target_score IS NULL OR target_score > 0",
            name="ck_target_positive",
        ),
    )

    def __repr__(self):
        return f"<Sport {self.name} ({self.scoring_type})>"

    def to_dict(self):
        return {
            "id":                self.id,
            "name":              self.name,
            "scoring_type":      self.scoring_type,
            "target_score":      self.target_score,
            "win_by_two":        self.win_by_two,
            "score_cap":         self.score_cap,
            "match_winner_rule": self.match_winner_rule,
            "allows_draw":       self.allows_draw,
        }


class Match(db.Model):
    __tablename__ = "matches"

    id         = db.Column(db.Integer, primary_key=True)
    sport_id   = db.Column(db.Integer, db.ForeignKey("sports.id"),  nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=False)
    winner_id  = db.Column(db.Integer, db.ForeignKey("users.id"),   nullable=True)

    # result is only populated for result-only sports (chess).
    # For numeric sports the winner is inferred from game scores.
    result       = db.Column(db.String(10),  nullable=True)   # 'win' | 'loss' | 'draw'
    played_at    = db.Column(db.DateTime, default=datetime.utcnow)
    location     = db.Column(db.String(200), nullable=True)
    confirmed    = db.Column(db.Boolean,  default=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)      # set when opponent confirms

    sport   = db.relationship("Sport", back_populates="matches")
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    winner  = db.relationship("User", foreign_keys=[winner_id])
    games   = db.relationship(
        "Game",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="Game.game_number",
    )

    def score_summary(self):
        """Aggregate game-level scores into a match-level tally.

        Returns:
            dict: {'player1_games': int, 'player2_games': int}
        """
        p1 = p2 = 0
        for g in self.games:
            if g.score_p1 is None or g.score_p2 is None:
                continue
            if g.score_p1 > g.score_p2:
                p1 += 1
            elif g.score_p2 > g.score_p1:
                p2 += 1
        return {"player1_games": p1, "player2_games": p2}

    def confirm(self):
        """Mark this match as confirmed by the opponent."""
        self.confirmed    = True
        self.confirmed_at = datetime.utcnow()

    def __repr__(self):
        return (
            f"<Match {self.id}: player {self.player1_id} vs "
            f"player {self.player2_id} ({self.sport_id})>"
        )


class Game(db.Model):
    """One row per game/set within a match.

    score_p1 and score_p2 are nullable so result-only sports (chess)
    can still use this table structure if needed, but typically
    chess matches will have no Game rows at all.
    """
    __tablename__ = "games"

    id          = db.Column(db.Integer, primary_key=True)
    match_id    = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    game_number = db.Column(db.Integer, nullable=False)   # 1, 2, 3 …
    score_p1    = db.Column(db.Integer, nullable=True)
    score_p2    = db.Column(db.Integer, nullable=True)

    match = db.relationship("Match", back_populates="games")

    __table_args__ = (
        # Prevent two rows for the same game number in the same match
        db.UniqueConstraint("match_id", "game_number", name="uix_match_game_number"),
    )

    def __repr__(self):
        return f"<Game match={self.match_id} #{self.game_number}: {self.score_p1}-{self.score_p2}>"


class FriendRequest(db.Model):
    __tablename__ = "friend_requests"

    id           = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status       = db.Column(
        db.String(32),
        nullable=False,
        default=FriendRequestStatus.pending.value,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    from_user = db.relationship(
        "User", foreign_keys=[from_user_id], back_populates="sent_requests"
    )
    to_user = db.relationship(
        "User", foreign_keys=[to_user_id], back_populates="received_requests"
    )

    __table_args__ = (
        # A user can only send one request to any given person
        db.UniqueConstraint("from_user_id", "to_user_id", name="uix_friend_request_unique"),
    )

    def accept(self):
        self.status = FriendRequestStatus.accepted.value

    def decline(self):
        self.status = FriendRequestStatus.declined.value

    def __repr__(self):
        return (
            f"<FriendRequest {self.from_user_id} → {self.to_user_id} ({self.status})>"
        )


class PushSubscription(db.Model):
    """Stores a Web Push subscription for one user on one device.

    A user can have multiple subscriptions (phone + tablet etc).
    Expired subscriptions are cleaned up automatically when a push fails.
    """
    __tablename__ = "push_subscriptions"

    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"),
                                  nullable=False)
    # The push endpoint URL — unique per device
    endpoint          = db.Column(db.Text, nullable=False)
    # Full subscription JSON including keys
    subscription_json = db.Column(db.Text, nullable=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref(
        "push_subscriptions", cascade="all, delete-orphan"
    ))

    __table_args__ = (
        db.UniqueConstraint("user_id", "endpoint", name="uix_user_endpoint"),
    )

    def __repr__(self):
        return f"<PushSubscription user={self.user_id}>"