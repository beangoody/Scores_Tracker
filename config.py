"""config.py
Flask configuration classes for Trackr.
"""

import os
from pathlib import Path

basedir = Path(__file__).resolve().parent


def _fix_postgres_url(url):
    """Railway provides postgres:// but SQLAlchemy needs postgresql://"""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False


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
    # These are evaluated when the class is loaded, not as properties,
    # so Flask-SQLAlchemy can read them correctly from the config dict.
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = (
        _fix_postgres_url(os.environ.get("DATABASE_URL")) or ""
    )


config_map = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}