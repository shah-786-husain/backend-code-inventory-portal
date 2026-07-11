from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.user_service import (
    get_users_list,
    get_user_by_id_service,
    create_user_service,
    update_user_service,
    toggle_user_status_service,
    get_roles_list_service,
    get_permissions_list_service
)
from services.assignment_service import get_user_items_service

user_bp = Blueprint("user", __name__)

@user_bp.route("", methods=["GET"])
@token_required
@role_required(["admin"])
def list_users():
    try:
        res = get_users_list(request.args)
        if 'page' in request.args:
            return jsonify({
                'items': res['users'],
                'pagination': res['pagination']
            }), 200
        else:
            return jsonify({"users": res['users']}), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch users", "error": str(e)}), 500

@user_bp.route("/<user_id>", methods=["GET"])
@token_required
@role_required(["admin"])
def get_user_by_id(user_id):
    try:
        user = get_user_by_id_service(user_id)
        if not user:
            return jsonify({"message": "User not found"}), 404
        return jsonify({"user": user}), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch user details", "error": str(e)}), 500

@user_bp.route("", methods=["POST"])
@token_required
@role_required(["admin"])
def create_user():
    try:
        data = request.get_json() or {}
        new_id = create_user_service(data, request.user)
        return jsonify({"message": "User created successfully", "id": new_id}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to create user", "error": str(e)}), 500

@user_bp.route("/<user_id>", methods=["PATCH"])
@token_required
@role_required(["admin"])
def update_user(user_id):
    try:
        data = request.get_json() or {}
        update_user_service(user_id, data, request.user)
        return jsonify({"message": "User updated successfully"}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to update user", "error": str(e)}), 500

@user_bp.route("/<user_id>/status", methods=["PATCH"])
@token_required
@role_required(["admin"])
def toggle_user_status(user_id):
    try:
        data = request.get_json() or {}
        toggle_user_status_service(user_id, data, request.user)
        return jsonify({"message": "User status updated successfully"}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to toggle status", "error": str(e)}), 500

@user_bp.route("/<user_id>/reset-password", methods=["POST"])
@token_required
@role_required(["admin"])
def reset_password(user_id):
    try:
        data = request.get_json() or {}
        password = data.get("password")
        if not password:
            return jsonify({"message": "Password is required"}), 400
        update_user_service(user_id, {"password": password}, request.user)
        return jsonify({"message": "Password reset successfully"}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to reset password", "error": str(e)}), 500

@user_bp.route("/<user_id>/items", methods=["GET"])
@token_required
def get_user_items(user_id):
    try:
        # Allow only admin, store_head or the user themselves to view these items
        if request.user['role'] not in ['admin', 'store_head'] and request.user['id'] != str(user_id):
            return jsonify({
                "success": False,
                "message": "Access forbidden: You can only view your own items",
                "errorCode": "AUTH_ROLE_FORBIDDEN",
                "details": None
            }), 403
            
        items = get_user_items_service(user_id)
        return jsonify(items), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to fetch user items", "error": str(e)}), 500

@user_bp.route("/roles", methods=["GET"])
@token_required
@role_required(["admin"])
def list_roles():
    try:
        roles = get_roles_list_service()
        return jsonify({"roles": roles}), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch roles", "error": str(e)}), 500

@user_bp.route("/permissions", methods=["GET"])
@token_required
@role_required(["admin"])
def list_permissions():
    try:
        perms = get_permissions_list_service()
        return jsonify({"permissions": perms}), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch permissions", "error": str(e)}), 500
