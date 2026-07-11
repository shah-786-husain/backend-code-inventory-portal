from datetime import datetime
from bson import ObjectId
from utils.db import db

def get_dict_diff(old_dict, new_dict, ignore_keys=None):
    """Computes the difference between two dicts. Returns (oldValue, newValue)."""
    if not old_dict and not new_dict:
        return None, None
        
    old_dict = old_dict or {}
    new_dict = new_dict or {}
    ignore_keys = ignore_keys or ['updatedAt', 'createdAt', '_id', 'id']
    
    old_val = {}
    new_val = {}
    
    all_keys = set(old_dict.keys()).union(set(new_dict.keys()))
    for k in all_keys:
        if k in ignore_keys:
            continue
        v1 = old_dict.get(k)
        v2 = new_dict.get(k)
        if v1 != v2:
            old_val[k] = v1
            new_val[k] = v2
            
    if not old_val and not new_val:
        return None, None
        
    return old_val, new_val


def sanitize_objids(val):
    if isinstance(val, list):
        return [sanitize_objids(v) for v in val]
    elif isinstance(val, dict):
        return {k: sanitize_objids(v) for k, v in val.items()}
    elif isinstance(val, ObjectId):
        return str(val)
    elif isinstance(val, datetime):
        return val.isoformat()
    return val


def log_audit(action, details, performed_by_id, performed_by_email, entity_type=None, entity_id=None, old_value=None, new_value=None, ip_address=None):
    try:
        log_entry = {
            "action": action,
            "details": details,
            "entityType": entity_type,
            "entityId": entity_id,
            "oldValue": sanitize_objids(old_value),
            "newValue": sanitize_objids(new_value),
            "performedBy": ObjectId(performed_by_id) if performed_by_id else None,
            "performedByUsername": performed_by_email,
            "ipAddress": ip_address,
            "timestamp": datetime.utcnow()
        }
        db.audit_logs.insert_one(log_entry)
    except Exception as e:
        print(f"Failed to write audit log: {e}")

def list_audit_logs(args=None):
    args = args or {}
    page = int(args.get('page', 1))
    limit = int(args.get('limit', 20))
    skip = (page - 1) * limit
    
    query = {}
    search = args.get('search', '').strip()
    if search:
        query['$or'] = [
            {'action': {'$regex': search, '$options': 'i'}},
            {'details': {'$regex': search, '$options': 'i'}},
            {'performedByUsername': {'$regex': search, '$options': 'i'}}
        ]
        
    action_filter = args.get('action', '').strip()
    if action_filter:
        query['action'] = action_filter

    entity_type = args.get('entityType', '').strip()
    if entity_type:
        query['entityType'] = entity_type

    entity_id = args.get('entityId', '').strip()
    if entity_id:
        query['entityId'] = entity_id

    user_filter = args.get('user', '').strip()
    if user_filter:
        query['performedByUsername'] = {'$regex': user_filter, '$options': 'i'}

    start_date = args.get('startDate', '').strip()
    end_date = args.get('endDate', '').strip()
    if start_date or end_date:
        query['timestamp'] = {}
        if start_date:
            try:
                if len(start_date) == 10:
                    query['timestamp']['$gte'] = datetime.strptime(start_date, "%Y-%m-%d")
                else:
                    query['timestamp']['$gte'] = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                pass
        if end_date:
            try:
                if len(end_date) == 10:
                    query['timestamp']['$lte'] = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                else:
                    query['timestamp']['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                pass
        
    total = db.audit_logs.count_documents(query)
    docs = list(db.audit_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit))
    
    formatted_logs = []
    for log in docs:
        formatted_logs.append({
            'id': str(log['_id']),
            'action': log.get('action', ''),
            'details': log.get('details', ''),
            'entityType': log.get('entityType'),
            'entityId': sanitize_objids(log.get('entityId')),
            'oldValue': sanitize_objids(log.get('oldValue')),
            'newValue': sanitize_objids(log.get('newValue')),
            'performedBy': str(log['performedBy']) if log.get('performedBy') else None,
            'performedByUsername': log.get('performedByUsername', 'System'),
            'ipAddress': log.get('ipAddress'),
            'timestamp': log['timestamp'].isoformat() if log.get('timestamp') else ''
        })
        
    return {
        'logs': formatted_logs,
        'total': total,
        'page': page,
        'limit': limit,
        'totalPages': (total + limit - 1) // limit
    }
