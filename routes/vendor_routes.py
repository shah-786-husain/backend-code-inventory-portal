from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.vendor_service import (
    create_vendor,
    list_vendors,
    get_vendor_detail,
    update_vendor,
    toggle_vendor_status,
    get_vendor_dashboard_metrics,
    get_vendor_specific_metrics
)

vendor_bp = Blueprint("vendors", __name__)

@vendor_bp.route("", methods=["POST"])
@token_required
@role_required(["store_head", "admin"])
def add_vendor():
    try:
        user_email = request.user["email"]
        data = request.get_json()
        vendor = create_vendor(data, user_email)
        return jsonify({
            "success": True,
            "message": "Vendor created successfully",
            "data": vendor
        }), 201
    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "errorCode": "BAD_REQUEST"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to create vendor",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("", methods=["GET"])
@token_required
def query_vendors():
    try:
        data = list_vendors(request.args)
        return jsonify({
            "success": True,
            "message": "Vendors retrieved successfully",
            "data": data
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to retrieve vendors",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("/dashboard", methods=["GET"])
@token_required
def get_dashboard_metrics():
    try:
        metrics = get_vendor_dashboard_metrics()
        return jsonify({
            "success": True,
            "message": "Vendor dashboard fetched successfully",
            "data": metrics
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to retrieve vendor dashboard metrics",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("/<string:vendor_id>", methods=["GET"])
@token_required
def get_vendor(vendor_id):
    try:
        vendor = get_vendor_detail(vendor_id)
        if not vendor:
            return jsonify({
                "success": False,
                "message": "Vendor not found",
                "errorCode": "NOT_FOUND"
            }), 404
        return jsonify({
            "success": True,
            "message": "Vendor details retrieved successfully",
            "data": vendor
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to retrieve vendor details",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("/<string:vendor_id>", methods=["PATCH"])
@token_required
@role_required(["store_head", "admin"])
def edit_vendor(vendor_id):
    try:
        user_email = request.user["email"]
        data = request.get_json()
        vendor = update_vendor(vendor_id, data, user_email)
        return jsonify({
            "success": True,
            "message": "Vendor updated successfully",
            "data": vendor
        }), 200
    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "errorCode": "BAD_REQUEST"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to update vendor",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("/<string:vendor_id>/status", methods=["PATCH"])
@token_required
@role_required(["store_head", "admin"])
def change_vendor_status(vendor_id):
    try:
        user_email = request.user["email"]
        vendor = toggle_vendor_status(vendor_id, user_email)
        return jsonify({
            "success": True,
            "message": "Vendor status updated successfully",
            "data": vendor
        }), 200
    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "errorCode": "BAD_REQUEST"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to update vendor status",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500

@vendor_bp.route("/<string:vendor_id>/metrics", methods=["GET"])
@token_required
def get_vendor_metrics_route(vendor_id):
    try:
        metrics = get_vendor_specific_metrics(vendor_id)
        return jsonify({
            "success": True,
            "message": "Vendor specific metrics retrieved successfully",
            "data": metrics
        }), 200
    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "errorCode": "BAD_REQUEST"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to retrieve vendor metrics",
            "errorCode": "INTERNAL_SERVER_ERROR",
            "details": str(e)
        }), 500
