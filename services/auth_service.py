"""
Authentication service layer for the Inventory & Asset Management Portal.
Provides a `login_service` function that handles email or username based login,
issues JWT tokens, and returns user data.
Uses `APIError` for standardized error handling.
"""

from utils.db import db
from utils.password_helper import check_password
from utils.jwt_helper import generate_token
from utils.errors import APIError, ErrorCode


def login_service(identifier: str, password: str):
    """Authenticate a user using email or username.

    Parameters
    ----------
    identifier: str
        Email address or username supplied by the client.
    password: str
        Plain‑text password.

    Returns
    -------
    dict
        ``{"token": <jwt>, "user": {...}}``
    """
    if not identifier or not password:
        raise APIError(
            "Email/username and password are required",
            ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    identifier = identifier.strip()
    # Determine if identifier looks like an email (contains '@')
    query = {"email": identifier.lower()} if "@" in identifier else {"username": identifier}
    user = db.users.find_one(query)
    if not user:
        raise APIError(
            "Invalid credentials",
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            status_code=401,
        )

    if not user.get("isActive", True):
        raise APIError(
            "User account is inactive",
            ErrorCode.AUTH_ACCOUNT_INACTIVE,
            status_code=403,
        )

    if not check_password(password, user["password"]):
        raise APIError(
            "Invalid credentials",
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            status_code=401,
        )

    token = generate_token(user)
    role_val = user.get("role") or "viewer"
    normalized_role = role_val.lower().replace(" ", "_")
    return {
        "token": token,
        "user": {
            "id": str(user["_id"]),
            "username": user.get("username", ""),
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "role": normalized_role,
        },
    }


def update_profile_service(user_id: str, data: dict, ip_address: str = None):
    from bson import ObjectId
    from datetime import datetime
    
    username = data.get('username', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    department = data.get('department', '').strip()

    if not username or not email:
        raise APIError("Username and email are required", ErrorCode.VALIDATION_ERROR, status_code=400)

    # Check email uniqueness (exclude current user)
    existing_email = db.users.find_one({'email': email, '_id': {'$ne': ObjectId(user_id)}})
    if existing_email:
        raise APIError("Email already exists", ErrorCode.DUPLICATE_RESOURCE, status_code=400)

    # Check username uniqueness (exclude current user)
    existing_username = db.users.find_one({'username': username, '_id': {'$ne': ObjectId(user_id)}})
    if existing_username:
        raise APIError("Username already exists", ErrorCode.DUPLICATE_RESOURCE, status_code=400)

    # Fetch old user to compute diff
    old_user = db.users.find_one({'_id': ObjectId(user_id)})
    if not old_user:
        raise APIError("User not found", ErrorCode.RESOURCE_NOT_FOUND, status_code=404)

    update_fields = {
        'username': username,
        'name': name or username,
        'email': email,
        'phone': phone,
        'department': department,
        'updatedAt': datetime.utcnow()
    }

    db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_fields})
    new_user = db.users.find_one({'_id': ObjectId(user_id)})

    # Log audit
    from services.audit_service import log_audit, get_dict_diff
    old_clean = old_user.copy()
    old_clean.pop('password', None)
    old_clean['_id'] = str(old_clean['_id'])
    
    new_clean = new_user.copy()
    new_clean.pop('password', None)
    new_clean['_id'] = str(new_clean['_id'])

    for doc in [old_clean, new_clean]:
        for k in ['createdAt', 'updatedAt']:
            if isinstance(doc.get(k), datetime):
                doc[k] = doc[k].isoformat()

    old_val, new_val = get_dict_diff(old_clean, new_clean)

    log_audit(
        action='user_updated',
        details=f"User '{username}' updated their own profile details",
        performed_by_id=user_id,
        performed_by_email=new_user['email'],
        entity_type='user',
        entity_id=str(user_id),
        old_value=old_val,
        new_value=new_val,
        ip_address=ip_address
    )

    role_val = new_user.get('role') or 'viewer'
    normalized_role = role_val.lower().replace(' ', '_')
    return {
        'id': str(new_user['_id']),
        'username': new_user.get('username', ''),
        'name': new_user.get('name', ''),
        'email': new_user['email'],
        'role': normalized_role,
        'department': new_user.get('department', ''),
        'phone': new_user.get('phone', '')
    }


def change_password_service(user_id: str, data: dict, ip_address: str = None):
    from bson import ObjectId
    from datetime import datetime
    
    old_password = data.get('oldPassword', '').strip()
    new_password = data.get('newPassword', '').strip()

    if not old_password or not new_password:
        raise APIError("Current password and new password are required", ErrorCode.VALIDATION_ERROR, status_code=400)

    if len(new_password) < 8:
        raise APIError("New password must be at least 8 characters long", ErrorCode.VALIDATION_ERROR, status_code=400)

    user = db.users.find_one({'_id': ObjectId(user_id)})
    if not user:
        raise APIError("User not found", ErrorCode.RESOURCE_NOT_FOUND, status_code=404)

    from utils.password_helper import hash_password
    if not check_password(old_password, user['password']):
        raise APIError("Current password is incorrect", ErrorCode.AUTH_INVALID_CREDENTIALS, status_code=401)

    hashed_pwd = hash_password(new_password)
    db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'password': hashed_pwd, 'updatedAt': datetime.utcnow()}})

    # Log audit
    from services.audit_service import log_audit
    log_audit(
        action='user_updated',
        details=f"User '{user.get('username')}' reset their own password",
        performed_by_id=user_id,
        performed_by_email=user['email'],
        entity_type='user',
        entity_id=str(user_id),
        old_value=None,
        new_value=None,
        ip_address=ip_address
    )
    return True
