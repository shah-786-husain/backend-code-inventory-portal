from functools import wraps
from flask import request, jsonify

def role_required(*roles):
    # Support both list/tuple (e.g. ['admin', 'store_head']) and positional arguments (e.g. 'admin', 'store_head')
    allowed_roles = roles
    if len(roles) == 1 and isinstance(roles[0], (list, tuple)):
        allowed_roles = roles[0]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'user'):
                return jsonify({
                    "success": False,
                    "message": "Authentication required",
                    "errorCode": "AUTH_TOKEN_MISSING",
                    "details": None
                }), 401
            if request.user['role'] not in allowed_roles:
                return jsonify({
                    "success": False,
                    "message": "Access forbidden for this role",
                    "errorCode": "AUTH_ROLE_FORBIDDEN",
                    "details": None
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
