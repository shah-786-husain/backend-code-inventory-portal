from flask import Blueprint, request, jsonify
from utils.errors import APIError, ErrorCode
from services.auth_service import login_service
from utils.jwt_helper import token_required

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        identifier = data.get('email') or data.get('username')
        password = data.get('password', '').strip()

        if not identifier or not password:
            raise APIError('Email/username and password are required', ErrorCode.VALIDATION_ERROR, status_code=400)

        result = login_service(identifier, password)
        return jsonify({
            'message': 'Login successful',
            'token': result['token'],
            'user': result['user']
        }), 200
    except APIError as api_err:
        return jsonify({'message': api_err.message, 'code': api_err.code}), api_err.status_code
    except Exception as e:
        # Unexpected error
        return jsonify({'message': 'Server error during login', 'error': str(e)}), 500

@auth_bp.route("/me", methods=["GET"])
@token_required
def me():
    return jsonify({"user": request.user}), 200


@auth_bp.route("/profile", methods=["PUT"])
@token_required
def update_profile():
    from services.auth_service import update_profile_service
    try:
        data = request.get_json() or {}
        user_id = request.user['id']
        updated_user = update_profile_service(user_id, data, request.remote_addr)
        return jsonify({
            "message": "Profile updated successfully",
            "user": updated_user
        }), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to update profile", "error": str(e)}), 500


@auth_bp.route("/change-password", methods=["POST"])
@token_required
def change_password():
    from services.auth_service import change_password_service
    try:
        data = request.get_json() or {}
        user_id = request.user['id']
        change_password_service(user_id, data, request.remote_addr)
        return jsonify({"message": "Password changed successfully"}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to change password", "error": str(e)}), 500