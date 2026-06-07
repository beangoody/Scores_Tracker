"""seeds/seed_sports.py
Populate the sports table with the default supported sports.

Run once after creating the database:
    python seeds/seed_sports.py

Adding a new sport in future = add one dict to SPORTS below and re-run.
No code changes needed anywhere else.
"""

import sys
import os

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.models import db, Sport

SPORTS = [
    {
        "name":               "Squash",
        "scoring_type":       "numeric",
        "target_score":       11,
        "win_by_two":         True,
        "score_cap":          None,
        "match_winner_rule":  "most_games",
        "allows_draw":        False,
    },
    {
        "name":               "Tennis",
        "scoring_type":       "numeric",
        "target_score":       6,
        "win_by_two":         True,
        "score_cap":          7,       # tiebreak cap
        "match_winner_rule":  "sets",
        "allows_draw":        False,
    },
    {
        "name":               "Padel",
        "scoring_type":       "numeric",
        "target_score":       6,
        "win_by_two":         True,
        "score_cap":          7,       # tiebreak cap
        "match_winner_rule":  "sets",
        "allows_draw":        False,
    },
    {
        "name":               "Badminton",
        "scoring_type":       "numeric",
        "target_score":       21,
        "win_by_two":         True,
        "score_cap":          30,      # hard cap at 30 per BWF rules
        "match_winner_rule":  "most_games",
        "allows_draw":        False,
    },
    {
        "name":               "Table Tennis",
        "scoring_type":       "numeric",
        "target_score":       11,
        "win_by_two":         True,
        "score_cap":          None,
        "match_winner_rule":  "most_games",
        "allows_draw":        False,
    },
    {
        "name":               "Chess",
        "scoring_type":       "result",
        "target_score":       None,
        "win_by_two":         False,
        "score_cap":          None,
        "match_winner_rule":  None,
        "allows_draw":        True,
    },
]


def seed():
    app = create_app("development")
    with app.app_context():
        added = 0
        skipped = 0
        for data in SPORTS:
            exists = Sport.query.filter_by(name=data["name"]).first()
            if exists:
                print(f"  skip  {data['name']} (already exists)")
                skipped += 1
                continue
            sport = Sport(**data)
            db.session.add(sport)
            print(f"  add   {data['name']}")
            added += 1

        db.session.commit()
        print(f"\nDone — {added} added, {skipped} skipped.")


if __name__ == "__main__":
    seed()