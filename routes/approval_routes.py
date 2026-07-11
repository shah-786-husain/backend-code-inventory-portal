from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.approval_engine_service import (
    submit_to_approvals,
    process_step_action,
    list_pending_reviews,
    list_user_submissions,
    get_approval_details
)

approval_bp = Blueprint("approvals", __name__)

@approval_bp.route("/submit", methods=["POST"])
@token_required
def submit_approval():
    try:
        user_id = request.user["id"]
        user_email = request.user["email"]
        data = request.get_json()
        
        target_type = data.get("targetType")
        target_id = data.get("targetId")
        summary_snapshot = data.get("summarySnapshot", {})
        
        if not target_type or not target_id:
            return jsonify({"message": "targetType and targetId are required"}), 400
            
        approval_id = submit_to_approvals(target_type, target_id, summary_snapshot, user_id, user_email)
        return jsonify({"message": "Approval request submitted successfully", "approvalId": approval_id}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to submit approval", "error": str(e)}), 500

@approval_bp.route("", methods=["GET"])
@token_required
def query_approvals():
    try:
        user = request.user
        scope = request.args.get("scope", "pending")
        status_filter = request.args.get("status", "pending")
        target_type_filter = request.args.get("targetType")
        
        if scope == "submissions":
            data = list_user_submissions(user["id"])
            return jsonify({"approvals": data}), 200
        else:
            data = list_pending_reviews(user, status_filter=status_filter, target_type_filter=target_type_filter)
            return jsonify({"approvals": data}), 200
    except Exception as e:
        return jsonify({"message": "Failed to query approvals", "error": str(e)}), 500

@approval_bp.route("/<string:approval_id>", methods=["GET"])
@token_required
def get_approval(approval_id):
    try:
        data = get_approval_details(approval_id)
        if not data:
            return jsonify({"message": "Approval request not found"}), 404
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve approval details", "error": str(e)}), 500

@approval_bp.route("/<string:approval_id>/action", methods=["POST"])
@token_required
def submit_approval_action(approval_id):
    try:
        reviewer = request.user
        data = request.get_json() or {}
        action = data.get("action")
        comments = data.get("comments", "")
        custom_data = data.get("customData", {})
        
        if not action or action not in ["approve", "reject", "send_back"]:
            return jsonify({"message": "Action must be approve, reject, or send_back"}), 400
            
        new_status = process_step_action(approval_id, action, comments, reviewer, custom_data)
        return jsonify({"message": f"Approval {action} processed successfully", "status": new_status}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to submit approval action", "error": str(e)}), 500
