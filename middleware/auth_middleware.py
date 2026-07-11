from functools import wraps
from flask import request, jsonify
from utils.jwt_helper import decode_token
from utils.db import db
from bson import ObjectId

def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({
                "success": False,
                "message": "Token is missing",
                "errorCode": "AUTH_TOKEN_MISSING",
                "details": None
            }), 401
        
        try:
            payload = decode_token(token)
            current_user = db.users.find_one({'_id': ObjectId(payload['user_id'])})
            if not current_user:
                return jsonify({
                    "success": False,
                    "message": "User not found",
                    "errorCode": "AUTH_USER_NOT_FOUND",
                    "details": None
                }), 401
            if not current_user.get('isActive', True):
                return jsonify({
                    "success": False,
                    "message": "User account is inactive",
                    "errorCode": "AUTH_ACCOUNT_INACTIVE",
                    "details": None
                }), 403
            
            # Make user context available on the Flask request object
            role_val = current_user.get('role') or 'viewer'
            normalized_role = role_val.lower().replace(' ', '_')
            request.user = {
                'id': str(current_user['_id']),
                'username': current_user.get('username', ''),
                'name': current_user.get('name'),
                'email': current_user.get('email', ''),
                'role': normalized_role
            }
        except ValueError as e:
            err_msg = str(e)
            err_code = "AUTH_TOKEN_EXPIRED" if "expired" in err_msg.lower() else "AUTH_TOKEN_INVALID"
            return jsonify({
                "success": False,
                "message": err_msg,
                "errorCode": err_code,
                "details": None
            }), 401
        except Exception as e:
            return jsonify({
                "success": False,
                "message": "Authentication failed",
                "errorCode": "AUTH_TOKEN_INVALID",
                "details": str(e)
            }), 401
            
        return f(*args, **kwargs)
    return decorated
