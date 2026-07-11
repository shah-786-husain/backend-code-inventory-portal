from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.audit_log_service import list_audit_logs

audit_log_bp = Blueprint("audit_log", __name__)

@audit_log_bp.route("", methods=["GET"])
@token_required
@role_required(["admin"])
def get_audit_logs():
    try:
        logs_data = list_audit_logs(request.args)
        return jsonify(logs_data), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch audit logs", "error": str(e)}), 500
