"""config.py
Flask configuration classes for Trackr.

Usage in app factory:
    from config import config_map
    app.config.from_object(config_map[os.environ.get("FLASK_ENV", "development")])
"""

import os
from pathlib import Path

basedir = Path(__file__).resolve().parent


def _fix_postgres_url(url):
    """Railway and Heroku provide DATABASE_URL starting with postgres://
    but SQLAlchemy 1.4+ requires postgresql://. Fix it silently.
    """
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """Base configuration shared across all environments."""
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-in-production")
    SQLALCHEMY_DATABASE_URI = (
        _fix_postgres_url(os.environ.get("DATABASE_URL"))
        or f"sqlite:///{basedir / 'trackr_dev.db'}"
    )


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False

    @property
    def SECRET_KEY(self):
        key = os.environ.get("SECRET_KEY")
        if not key:
            raise ValueError(
                "SECRET_KEY environment variable is not set."
            )
        return key

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        url = _fix_postgres_url(os.environ.get("DATABASE_URL"))
        if not url:
            raise ValueError(
                "DATABASE_URL environment variable is not set."
            )
        return url


config_map = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}