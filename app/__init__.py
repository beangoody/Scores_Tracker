"""app/__init__.py
Application factory for Trackr.

Usage:
    from app import create_app
    app = create_app("development")   # or "production", "testing"
"""

from flask import Flask
from flask_login import LoginManager

from config import config_map
from app.models import db, init_db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    # db.session.get() is the correct SQLAlchemy 2.x API (replaces Query.get)
    return db.session.get(User, int(user_id))


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__, instance_relative_config=False, template_folder="../templates")
    app.config.from_object(config_map.get(config_name, config_map["default"]))

    # Extensions
    init_db(app)
    login_manager.init_app(app)

    # Blueprints — imported here to avoid circular imports
    from app.auth    import auth_bp
    from app.matches import matches_bp
    from app.stats   import stats_bp
    from app.social  import social_bp
    from app.sports  import sports_bp
    from app.notifications import push_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(sports_bp)
    app.register_blueprint(push_bp)

    # Create tables for any models that don't exist yet.
    # In production you'd use Flask-Migrate instead, but this is
    # fine for development and gets you running immediately.
    with app.app_context():
        db.create_all()

    return app