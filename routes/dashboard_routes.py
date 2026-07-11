from flask import Blueprint, jsonify, request
from utils.jwt_helper import token_required
from services.dashboard_service import get_dashboard_summary, get_recent_activity

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/summary", methods=["GET"])
@token_required
def get_summary():
    try:
        summary = get_dashboard_summary(request.user)
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to fetch dashboard summary",
            "errorCode": "INTERNAL_ERROR",
            "details": str(e),
        }), 500


@dashboard_bp.route("/activity", methods=["GET"])
@token_required
def get_activity():
    try:
        limit = int(request.args.get("limit", 15))
        feed = get_recent_activity(request.user, limit=limit)
        return jsonify(feed), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to fetch dashboard activity feed",
            "errorCode": "INTERNAL_ERROR",
            "details": str(e),
        }), 500
