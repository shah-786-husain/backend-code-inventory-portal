from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.asset_request_service import (
    create_asset_request,
    list_asset_requests,
    get_asset_request_detail,
    approve_asset_request,
    reject_asset_request,
    cancel_asset_request,
    fulfill_asset_request
)

asset_request_bp = Blueprint("asset_requests", __name__)

@asset_request_bp.route("", methods=["POST"])
@token_required
@role_required(["team_member", "store_head", "admin"])
def submit_request():
    try:
        user_id = request.user["id"]
        user_email = request.user["email"]
        data = request.get_json()
        
        req = create_asset_request(data, user_id, user_email)
        return jsonify({"message": "Asset request submitted successfully", "request": req}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to submit request", "error": str(e)}), 500

@asset_request_bp.route("", methods=["GET"])
@token_required
def query_requests():
    try:
        user = request.user
        data = list_asset_requests(request.args, user)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve requests", "error": str(e)}), 500

@asset_request_bp.route("/<string:request_id>", methods=["GET"])
@token_required
def get_request_detail_route(request_id):
    try:
        user = request.user
        data = get_asset_request_detail(request_id, user)
        if not data:
            return jsonify({"message": "Request not found"}), 404
        return jsonify(data), 200
    except PermissionError as e:
        return jsonify({"message": str(e)}), 403
    except Exception as e:
        return jsonify({"message": "Failed to retrieve request details", "error": str(e)}), 500

@asset_request_bp.route("/<string:request_id>/approve", methods=["PATCH"])
@token_required
@role_required(["store_head", "admin"])
def approve_request_route(request_id):
    try:
        reviewer = request.user
        data = request.get_json(silent=True) or {}
        comments = data.get("remarks", data.get("comments", ""))
        
        req = approve_asset_request(request_id, comments, reviewer)
        return jsonify({"message": "Request approved successfully", "request": req}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to approve request", "error": str(e)}), 500

@asset_request_bp.route("/<string:request_id>/reject", methods=["PATCH"])
@token_required
@role_required(["store_head", "admin"])
def reject_request_route(request_id):
    try:
        reviewer = request.user
        data = request.get_json(silent=True) or {}
        reason = data.get("reason", data.get("rejectionReason", data.get("comments", "")))
        
        req = reject_asset_request(request_id, reason, reviewer)
        return jsonify({"message": "Request rejected successfully", "request": req}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to reject request", "error": str(e)}), 500

@asset_request_bp.route("/<string:request_id>/cancel", methods=["PATCH"])
@token_required
def cancel_request_route(request_id):
    try:
        user_id = request.user["id"]
        req = cancel_asset_request(request_id, user_id)
        return jsonify({"message": "Request cancelled successfully", "request": req}), 200
    except PermissionError as e:
        return jsonify({"message": str(e)}), 403
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to cancel request", "error": str(e)}), 500

@asset_request_bp.route("/<string:request_id>/fulfill", methods=["PATCH"])
@token_required
@role_required(["store_head", "admin"])
def fulfill_request_route(request_id):
    try:
        fulfiller = request.user
        data = request.get_json(silent=True) or {}
        transaction_ids = data.get("linkedTransactionIds", [])
        
        req = fulfill_asset_request(request_id, transaction_ids, fulfiller)
        return jsonify({"message": "Request marked as fulfilled successfully", "request": req}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to fulfill request", "error": str(e)}), 500
