"""run.py
Entry point for running Trackr locally.

Usage:
    python run.py

Environment variables:
    FLASK_ENV   — "development" (default) | "production" | "testing"
    SECRET_KEY  — required in production
"""

import os
from app import create_app

config_name = os.environ.get("FLASK_ENV", "development")
app = create_app(config_name)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",   # accessible on your local network (useful for phone testing)
        port=5000,
        debug=(config_name == "development"),
    )