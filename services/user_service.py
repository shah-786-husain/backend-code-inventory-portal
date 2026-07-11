import re
from datetime import datetime
from bson import ObjectId
from utils.db import db
from utils.password_helper import hash_password
from services.audit_service import log_audit, get_dict_diff
from flask import has_request_context, request

def _get_ip():
    return request.remote_addr if has_request_context() else None

def seed_roles_and_permissions():
    try:
        if db.roles.count_documents({}) == 0:
            db.roles.insert_many([
                {
                    "name": "admin",
                    "displayName": "Administrator",
                    "permissions": ["view_inventory", "manage_inventory", "log_transaction", "admin_reconciliation", "manage_invoices", "view_audit_logs", "manage_users"]
                },
                {
                    "name": "store_head",
                    "displayName": "Store Head",
                    "permissions": ["view_inventory", "manage_inventory", "log_transaction", "manage_invoices", "view_audit_logs"]
                },
                {
                    "name": "team_member",
                    "displayName": "Team Member",
                    "permissions": ["view_inventory"]
                },
                {
                    "name": "viewer",
                    "displayName": "Viewer",
                    "permissions": ["view_inventory"]
                }
            ])
        if db.permissions.count_documents({}) == 0:
            db.permissions.insert_many([
                { "name": "view_inventory", "description": "Read-only access to item catalog" },
                { "name": "manage_inventory", "description": "Create, edit, and delete catalog items" },
                { "name": "log_transaction", "description": "Issue, return, consume, transfer, repair, or adjust stock" },
                { "name": "admin_reconciliation", "description": "Reconcile inventory audits and corrections" },
                { "name": "manage_invoices", "description": "Upload and modify vendor invoice documents" },
                { "name": "view_audit_logs", "description": "View system activity and audit logs" },
                { "name": "manage_users", "description": "Create, edit, and disable user credentials" }
            ])
    except Exception:
        pass

# Call seed immediately on module import
seed_roles_and_permissions()

def get_users_list(filters=None):
    import math
    filters = filters or {}
    query = {}
    
    search = (filters.get('search') or '').strip()
    if search:
        query['$or'] = [
            {'username': {'$regex': search, '$options': 'i'}},
            {'email': {'$regex': search, '$options': 'i'}},
            {'name': {'$regex': search, '$options': 'i'}}
        ]
        
    if filters.get('role'):
        query['role'] = filters.get('role')
        
    status = filters.get('status')
    if status:
        query['isActive'] = (status.lower() == 'active')
        
    if filters.get('department'):
        query['department'] = {'$regex': filters.get('department'), '$options': 'i'}
        
    # Pagination
    try:
        page = max(1, int(filters.get('page', 1)))
    except Exception:
        page = 1
        
    try:
        limit = max(1, int(filters.get('limit', 20)))
    except Exception:
        limit = 20
        
    skip = (page - 1) * limit
    
    sort_by = filters.get('sortBy', 'createdAt')
    if sort_by == 'status':
        sort_by = 'isActive'
        
    sort_order = -1 if filters.get('sortOrder', 'desc').lower() == 'desc' else 1
    
    total = db.users.count_documents(query)
    users = list(db.users.find(query, {'password': 0}).sort(sort_by, sort_order).skip(skip).limit(limit))
    
    formatted_users = []
    for user in users:
        role_val = user.get('role') or 'viewer'
        normalized_role = role_val.lower().replace(' ', '_')
        formatted_users.append({
            'id': str(user['_id']),
            'username': user.get('username', user.get('name', '')),
            'name': user.get('name', user.get('username', '')),
            'email': user.get('email', ''),
            'role': normalized_role,
            'status': 'active' if user.get('isActive', True) else 'inactive',
            'department': user.get('department', ''),
            'phone': user.get('phone', ''),
            'createdAt': user.get('createdAt', datetime.utcnow()).isoformat() if isinstance(user.get('createdAt'), datetime) else str(user.get('createdAt', ''))
        })
        
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    
    return {
        'users': formatted_users,
        'total': total,
        'page': page,
        'limit': limit,
        'totalPages': total_pages,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': total_pages
        }
    }

def get_user_by_id_service(user_id):
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)}, {'password': 0})
    except Exception:
        return None
    if not user:
        return None
    role_val = user.get('role') or 'viewer'
    normalized_role = role_val.lower().replace(' ', '_')
    return {
        'id': str(user['_id']),
        'username': user.get('username', user.get('name', '')),
        'name': user.get('name', user.get('username', '')),
        'email': user.get('email', ''),
        'role': normalized_role,
        'status': 'active' if user.get('isActive', True) else 'inactive',
        'department': user.get('department', ''),
        'phone': user.get('phone', ''),
        'createdAt': user.get('createdAt', datetime.utcnow()).isoformat() if isinstance(user.get('createdAt'), datetime) else str(user.get('createdAt', ''))
    }

def create_user_service(data, user_context):
    username = data.get('username', '').strip()
    name = data.get('name', username).strip() or username
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    role = data.get('role', 'team_member')
    department = data.get('department', '').strip()
    phone = data.get('phone', '').strip()
    
    if not username or not email or not password or not role:
        raise ValueError("Username, email, password, and role are required")
        
    if role not in ['admin', 'store_head', 'team_member', 'viewer']:
        raise ValueError("Invalid role specified")
        
    # Check password strength
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
        
    # Check uniqueness
    if db.users.find_one({'email': email}):
        raise ValueError("Email already exists")
    if db.users.find_one({'username': username}):
        raise ValueError("Username already exists")
        
    hashed_pwd = hash_password(password)
    
    new_user = {
        'username': username,
        'name': name,
        'email': email,
        'password': hashed_pwd,
        'role': role,
        'department': department,
        'phone': phone,
        'isActive': True,
        'createdAt': datetime.utcnow(),
        'updatedAt': datetime.utcnow()
    }
    
    result = db.users.insert_one(new_user)
    
    audit_new_user = new_user.copy()
    audit_new_user.pop('password', None)
    audit_new_user['_id'] = str(result.inserted_id)
    if 'createdAt' in audit_new_user:
        audit_new_user['createdAt'] = audit_new_user['createdAt'].isoformat()
    if 'updatedAt' in audit_new_user:
        audit_new_user['updatedAt'] = audit_new_user['updatedAt'].isoformat()

    log_audit(
        action='user_created', 
        details=f"Created user account '{username}' with role '{role}' and department '{department}'", 
        performed_by_id=user_context['id'], 
        performed_by_email=user_context['email'],
        entity_type='user',
        entity_id=str(result.inserted_id),
        new_value=audit_new_user,
        ip_address=_get_ip()
    )
    return str(result.inserted_id)

def update_user_service(user_id, data, user_context):
    update_fields = {}
    
    if 'username' in data:
        update_fields['username'] = data['username'].strip()
    if 'name' in data:
        update_fields['name'] = data['name'].strip()
    if 'email' in data:
        update_fields['email'] = data['email'].strip().lower()
    if 'role' in data:
        if data['role'] not in ['admin', 'store_head', 'team_member', 'viewer']:
            raise ValueError("Invalid role specified")
        update_fields['role'] = data['role']
    if 'department' in data:
        update_fields['department'] = data['department'].strip()
    if 'phone' in data:
        update_fields['phone'] = data['phone'].strip()
    if 'password' in data and data['password']:
        if len(data['password']) < 8:
            raise ValueError("Password must be at least 8 characters long")
        update_fields['password'] = hash_password(data['password'])
        
    if not update_fields:
        raise ValueError("No fields provided for update")
        
    update_fields['updatedAt'] = datetime.utcnow()
    
    # Fetch old user to compute diff
    old_user_doc = db.users.find_one({'_id': ObjectId(user_id)})
    
    db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_fields})
    
    # Fetch new user
    new_user_doc = db.users.find_one({'_id': ObjectId(user_id)})
    
    if old_user_doc and new_user_doc:
        old_clean = old_user_doc.copy()
        old_clean.pop('password', None)
        old_clean['_id'] = str(old_clean['_id'])
        if isinstance(old_clean.get('createdAt'), datetime):
            old_clean['createdAt'] = old_clean['createdAt'].isoformat()
        if isinstance(old_clean.get('updatedAt'), datetime):
            old_clean['updatedAt'] = old_clean['updatedAt'].isoformat()
            
        new_clean = new_user_doc.copy()
        new_clean.pop('password', None)
        new_clean['_id'] = str(new_clean['_id'])
        if isinstance(new_clean.get('createdAt'), datetime):
            new_clean['createdAt'] = new_clean['createdAt'].isoformat()
        if isinstance(new_clean.get('updatedAt'), datetime):
            new_clean['updatedAt'] = new_clean['updatedAt'].isoformat()
            
        old_val, new_val = get_dict_diff(old_clean, new_clean)
    else:
        old_val, new_val = None, None
        
    log_audit(
        action='user_updated', 
        details=f"Updated user account details for user ID {user_id}", 
        performed_by_id=user_context['id'], 
        performed_by_email=user_context['email'],
        entity_type='user',
        entity_id=str(user_id),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    
    # Trigger notification
    try:
        from services.notification_service import create_notification
        create_notification(
            user_id=user_id,
            message="Your account details have been updated.",
            type_="account_change",
            link="/dashboard"
        )
    except Exception as e:
        print(f"Failed to trigger user update notification: {e}")
        
    return True

def toggle_user_status_service(user_id, data, user_context):
    status = data.get('status')
    if status not in ['active', 'inactive']:
        raise ValueError("Status must be 'active' or 'inactive'")
        
    # Prevent self-deactivation
    if str(user_id) == user_context['id'] and status == 'inactive':
        raise ValueError("You cannot deactivate your own account")
        
    is_active = (status == 'active')
    
    old_user = db.users.find_one({'_id': ObjectId(user_id)})
    old_status = old_user.get('isActive', True) if old_user else True

    db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$set': {
                'isActive': is_active,
                'updatedAt': datetime.utcnow()
            }
        }
    )
    
    action = 'user_disabled' if not is_active else 'user_enabled'
    log_audit(
        action=action, 
        details=f"Toggled user ID {user_id} status to '{status}'", 
        performed_by_id=user_context['id'], 
        performed_by_email=user_context['email'],
        entity_type='user',
        entity_id=str(user_id),
        old_value={'isActive': old_status},
        new_value={'isActive': is_active},
        ip_address=_get_ip()
    )
    
    # Trigger notification
    try:
        from services.notification_service import create_notification
        create_notification(
            user_id=user_id,
            message=f"Your account status has been updated to '{status}'.",
            type_="account_change",
            link="/dashboard"
        )
    except Exception as e:
        print(f"Failed to trigger user toggle status notification: {e}")
        
    return True

def get_roles_list_service():
    roles = list(db.roles.find({}))
    formatted = []
    for role in roles:
        formatted.append({
            'name': role.get('name'),
            'displayName': role.get('displayName'),
            'permissions': role.get('permissions', [])
        })
    return formatted

def get_permissions_list_service():
    perms = list(db.permissions.find({}))
    formatted = []
    for perm in perms:
        formatted.append({
            'name': perm.get('name'),
            'description': perm.get('description')
        })
    return formatted
