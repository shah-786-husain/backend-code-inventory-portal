import jwt
import datetime
import os
from dotenv import load_dotenv
from flask import request, jsonify
from functools import wraps
from bson import ObjectId
from utils.db import db

load_dotenv()

# Fallback to local default secret if environment variable is not defined
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-inventory-key-change-in-prod")

def generate_token(user):
    # Token expiry uses the configurable hours from Config (default 24h)
    from config import Config
    expiry_seconds = Config.JWT_EXPIRY_HOURS * 3600
    role_val = user.get("role") or "viewer"
    normalized_role = role_val.lower().replace(" ", "_")
    payload = {
        "user_id": str(user["_id"]),
        "email": user.get("email", ""),
        "role": normalized_role,
        "username": user.get("username", ""),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(seconds=expiry_seconds)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token

def decode_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

# Import decorators from middleware modules to centralized jwt_helper
from middleware.auth_middleware import jwt_required
from middleware.role_middleware import role_required

# Backward compatibility alias
token_required = jwt_required