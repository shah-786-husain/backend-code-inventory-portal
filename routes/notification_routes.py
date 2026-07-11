import time
from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required
from services.notification_service import (
    list_notifications,
    mark_as_read,
    mark_all_read,
    archive_notification,
    archive_all,
    check_overdue_returns,
    check_maintenance_reminders
)

notification_bp = Blueprint("notifications", __name__)

LAST_SWEEP_TIME = 0.0

@notification_bp.route("", methods=["GET"])
@token_required
def get_notifications():
    try:
        global LAST_SWEEP_TIME
        current_time = time.time()
        # Trigger sweeps at most once every 5 minutes
        if current_time - LAST_SWEEP_TIME > 300:
            check_overdue_returns()
            check_maintenance_reminders()
            LAST_SWEEP_TIME = current_time
            
        user_id = request.user["id"]
        role = request.user.get("role")
        
        unread_only = request.args.get("unreadOnly", "false").lower() == "true"
        read_only = False if unread_only else None
        
        include_archived = request.args.get("includeArchived", "false").lower() == "true"
        
        data = list_notifications(user_id, role, read_only, include_archived)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch notifications", "error": str(e)}), 500

@notification_bp.route("/<string:notification_id>/read", methods=["PUT"])
@token_required
def read_notification(notification_id):
    try:
        user_id = request.user["id"]
        role = request.user.get("role")
        mark_as_read(notification_id, user_id, role)
        return jsonify({"message": "Notification marked as read"}), 200
    except PermissionError as e:
        return jsonify({"message": str(e)}), 403
    except ValueError as e:
        return jsonify({"message": str(e)}), 404
    except Exception as e:
        return jsonify({"message": "Failed to update notification", "error": str(e)}), 500

@notification_bp.route("/<string:notification_id>/archive", methods=["PUT"])
@token_required
def archive_notif(notification_id):
    try:
        user_id = request.user["id"]
        role = request.user.get("role")
        archive_notification(notification_id, user_id, role)
        return jsonify({"message": "Notification archived"}), 200
    except PermissionError as e:
        return jsonify({"message": str(e)}), 403
    except ValueError as e:
        return jsonify({"message": str(e)}), 404
    except Exception as e:
        return jsonify({"message": "Failed to archive notification", "error": str(e)}), 500

@notification_bp.route("/read-all", methods=["PUT"])
@token_required
def read_all_notifications():
    try:
        user_id = request.user["id"]
        role = request.user.get("role")
        mark_all_read(user_id, role)
        return jsonify({"message": "All notifications marked as read"}), 200
    except Exception as e:
        return jsonify({"message": "Failed to update notifications", "error": str(e)}), 500

@notification_bp.route("/archive-all", methods=["PUT"])
@token_required
def archive_all_notifications():
    try:
        user_id = request.user["id"]
        role = request.user.get("role")
        archive_all(user_id, role)
        return jsonify({"message": "All notifications archived"}), 200
    except Exception as e:
        return jsonify({"message": "Failed to archive notifications", "error": str(e)}), 500

