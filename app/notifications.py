"""app/notifications.py
Push notification blueprint for Trackr.

Handles saving push subscriptions and sending notifications
using the Web Push protocol with VAPID authentication.

Routes:
    POST /push/subscribe    — save a push subscription for the current user
    POST /push/unsubscribe  — remove a push subscription
    GET  /push/vapid-public — return the VAPID public key for the client
"""

import os
import json
import logging

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.models import db, PushSubscription

push_bp = Blueprint("push", __name__, url_prefix="/push")
logger  = logging.getLogger(__name__)


def send_push_notification(user_id: int, title: str, body: str, url: str = "/") -> int:
    """Send a push notification to all subscriptions for a user.

    Args:
        user_id: The recipient's user ID.
        title:   Notification title.
        body:    Notification body text.
        url:     URL to open when notification is tapped.

    Returns:
        Number of notifications successfully sent.
    """
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — push notifications disabled.")
        return 0

    vapid_private = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_email   = os.environ.get("VAPID_EMAIL", "mailto:admin@trackr.app")

    if not vapid_private:
        logger.warning("VAPID_PRIVATE_KEY not set — skipping push notification.")
        return 0

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return 0

    payload = json.dumps({
        "title": title,
        "body":  body,
        "url":   url,
        "icon":  "/static/icons/icon-192.png",
        "badge": "/static/icons/icon-192.png",
    })

    sent = 0
    dead = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info = json.loads(sub.subscription_json),
                data              = payload,
                vapid_private_key = vapid_private,
                vapid_claims      = {"sub": vapid_email},
            )
            sent += 1
        except Exception as exc:
            # 404/410 means the subscription is expired — mark for removal
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 410):
                dead.append(sub)
            else:
                logger.error(f"Push failed for subscription {sub.id}: {exc}")

    # Clean up expired subscriptions
    for sub in dead:
        db.session.delete(sub)
    if dead:
        db.session.commit()

    return sent


# ── Routes ────────────────────────────────────────────────────────────────────

@push_bp.route("/vapid-public")
def vapid_public_key():
    """Return the VAPID public key so the client can subscribe."""
    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return jsonify({"publicKey": key})


@push_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe():
    """Save a push subscription for the current user.

    Expects JSON body:
        { endpoint, keys: { p256dh, auth } }
    """
    data = request.get_json(silent=True)
    if not data or "endpoint" not in data:
        return jsonify({"error": "Invalid subscription data"}), 400

    endpoint         = data.get("endpoint")
    subscription_json = json.dumps(data)

    # Upsert — update if this endpoint already exists for this user
    existing = PushSubscription.query.filter_by(
        user_id  = current_user.id,
        endpoint = endpoint,
    ).first()

    if existing:
        existing.subscription_json = subscription_json
    else:
        db.session.add(PushSubscription(
            user_id           = current_user.id,
            endpoint          = endpoint,
            subscription_json = subscription_json,
        ))

    db.session.commit()
    return jsonify({"status": "subscribed"}), 201


@push_bp.route("/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    """Remove a push subscription."""
    data     = request.get_json(silent=True)
    endpoint = data.get("endpoint") if data else None

    if endpoint:
        PushSubscription.query.filter_by(
            user_id  = current_user.id,
            endpoint = endpoint,
        ).delete()
        db.session.commit()

    return jsonify({"status": "unsubscribed"}), 200