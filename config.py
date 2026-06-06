"""config.py
Flask configuration classes for Trackr.

Usage in app factory:
    from config import config_map
    app.config.from_object(config_map[os.environ.get("FLASK_ENV", "development")])
"""

import os
from pathlib import Path

basedir = Path(__file__).resolve().parent


class Config:
    """Base configuration — shared across all environments."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    # Fallback to a local SQLite file if DATABASE_URL is not set
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-in-production")
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{basedir / 'trackr_dev.db'}"
    )


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret"
    # In-memory SQLite — fast, isolated, never touches the dev database
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Disable CSRF protection in tests so forms can be submitted without tokens
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{basedir / 'trackr_prod.db'}"
    )

    @property
    def SECRET_KEY(self):
        key = os.environ.get("SECRET_KEY")
        if not key:
            raise ValueError(
                "SECRET_KEY environment variable is not set. "
                "Set it before running in production."
            )
        return key


config_map = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}