import datetime
from bson import ObjectId
from utils.db import db
from services.audit_service import log_audit, get_dict_diff

def _str_id(val):
    if not val:
        return None
    return str(val)

def _format_date(val):
    if not val:
        return ""
    if isinstance(val, datetime.datetime):
        return val.isoformat()
    return str(val)

def serialize_asset_request(d):
    if not d:
        return None
    
    # Map requested items safely
    items = d.get("requestedItems")
    if not items:
        # Fallback to legacy single item format if present
        if d.get("itemId") or d.get("itemName"):
            items = [{
                "itemId": _str_id(d.get("itemId")),
                "itemCode": d.get("itemCode", ""),
                "itemName": d.get("itemName", "Unknown Item"),
                "quantity": int(d.get("quantity", 1))
            }]
        else:
            items = []
            
    # Serialize items list safely converting any ObjectIds
    serialized_items = []
    for item in items:
        if not item:
            continue
        serialized_items.append({
            "itemId": _str_id(item.get("itemId")),
            "itemCode": item.get("itemCode", ""),
            "itemName": item.get("itemName", ""),
            "quantity": int(item.get("quantity", 0)),
            "status": item.get("status", "")
        })

    return {
        "id": str(d["_id"]),
        "requestId": d.get("requestId", d.get("requestCode")),
        "requestCode": d.get("requestCode"),
        "employeeId": _str_id(d.get("employeeId") or d.get("requesterId")),
        "employeeName": d.get("employeeName") or d.get("requesterName"),
        "employeeEmail": d.get("employeeEmail") or d.get("requesterEmail"),
        "departmentId": _str_id(d.get("departmentId")),
        "departmentName": d.get("departmentName"),
        "requestedItems": serialized_items,
        "items": serialized_items, # Return both for frontend compatibility
        "priority": d.get("priority", "medium"),
        "purpose": d.get("purpose", ""),
        "requiredFrom": _format_date(d.get("requiredFrom") or d.get("requiredDate")),
        "requiredUntil": _format_date(d.get("requiredUntil")),
        "status": d.get("status"),
        "approvalRemarks": d.get("approvalRemarks") or d.get("managerComments") or d.get("storeHeadComments"),
        "rejectionReason": d.get("rejectionReason") or d.get("rejectReason"),
        "approvedBy": _str_id(d.get("approvedBy") or d.get("managerId") or d.get("storeHeadId")),
        "approvedByName": d.get("approvedByName") or d.get("managerName") or d.get("storeHeadName"),
        "approvedAt": _format_date(d.get("approvedAt") or d.get("managerApprovalDate") or d.get("storeHeadApprovalDate")),
        "fulfilledBy": _str_id(d.get("fulfilledBy")),
        "fulfilledAt": _format_date(d.get("fulfilledAt")),
        "linkedTransactionIds": [_str_id(x) for x in d.get("linkedTransactionIds", []) if x] or ([_str_id(d.get("transactionId"))] if d.get("transactionId") else []),
        "createdAt": _format_date(d.get("createdAt")),
        "updatedAt": _format_date(d.get("updatedAt"))
    }

def create_asset_request(data, user_id, user_email):
    # Fetch user to get metadata
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise ValueError("User not found")
        
    requested_items = data.get("requestedItems", [])
    if not requested_items:
        raise ValueError("requestedItems list cannot be empty")
        
    for item in requested_items:
        qty = int(item.get("quantity", 0))
        if qty <= 0:
            raise ValueError(f"Requested quantity for item {item.get('itemCode', '')} must be greater than 0")
            
    # Calculate sequential requestCode
    current_month = datetime.datetime.utcnow().strftime("%Y%m")
    prefix = f"REQ-{current_month}-"
    count = db.asset_requests.count_documents({"requestId": {"$regex": f"^{prefix}"}})
    req_code = f"{prefix}{str(count + 1).zfill(4)}"
    
    def _parse_date(val):
        if not val:
            return None
        if isinstance(val, datetime.datetime):
            return val
        try:
            cleaned = val.replace("Z", "").split("+")[0]
            return datetime.datetime.fromisoformat(cleaned)
        except Exception:
            return val
            
    request_doc = {
        "requestId": req_code,
        "requestCode": req_code,
        "employeeId": str(user_id),
        "employeeName": user.get("username", user_email),
        "employeeEmail": user_email,
        "departmentId": user.get("department", ""),
        "departmentName": user.get("department", ""),
        "requestedItems": requested_items,
        "priority": data.get("priority", "medium"),
        "purpose": data.get("purpose", ""),
        "requiredFrom": _parse_date(data.get("requiredFrom")),
        "requiredUntil": _parse_date(data.get("requiredUntil")),
        "status": "PENDING",
        "approvalRemarks": None,
        "rejectionReason": None,
        "approvedBy": None,
        "approvedByName": None,
        "approvedAt": None,
        "fulfilledBy": None,
        "fulfilledAt": None,
        "linkedTransactionIds": [],
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }
    
    res = db.asset_requests.insert_one(request_doc)
    request_doc["_id"] = res.inserted_id
    
    log_audit(
        action="request_created",
        details=f"Asset Request {req_code} created by {user_email}",
        performed_by_id=user_id,
        performed_by_email=user_email,
        entity_type="asset_request",
        entity_id=str(res.inserted_id),
        new_value=serialize_asset_request(request_doc)
    )
    
    return serialize_asset_request(request_doc)

def list_asset_requests(args, user):
    page = int(args.get("page", 1))
    limit = int(args.get("limit", 20))
    skip = (page - 1) * limit
    
    role = user.get("role")
    user_id = str(user.get("id"))
    
    query = {}
    if role == "team_member":
        query["employeeId"] = user_id
        
    status_filter = args.get("status")
    if status_filter:
        query["status"] = status_filter
        
    employee_filter = args.get("employeeId")
    if employee_filter:
        query["employeeId"] = employee_filter
        
    search = args.get("search", "").strip()
    if search:
        query["$or"] = [
            {"requestCode": {"$regex": search, "$options": "i"}},
            {"employeeName": {"$regex": search, "$options": "i"}},
            {"employeeEmail": {"$regex": search, "$options": "i"}},
            {"purpose": {"$regex": search, "$options": "i"}},
            {"requestedItems.itemName": {"$regex": search, "$options": "i"}}
        ]
        
    total = db.asset_requests.count_documents(query)
    docs = list(db.asset_requests.find(query).sort("createdAt", -1).skip(skip).limit(limit))
    
    formatted = [serialize_asset_request(d) for d in docs]
    
    return {
        "items": formatted,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }

def get_asset_request_detail(request_id_str, user):
    req_doc = db.asset_requests.find_one({"_id": ObjectId(request_id_str)})
    if not req_doc:
        return None
        
    # Access control
    role = user.get("role")
    if role == "team_member" and req_doc.get("employeeId") != str(user.get("id")):
        raise PermissionError("Access denied to this asset request")
        
    return serialize_asset_request(req_doc)

def approve_asset_request(request_id_str, comments, reviewer):
    req_id_obj = ObjectId(request_id_str)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")
        
    if req["status"] != "PENDING":
        raise ValueError(f"Cannot approve request in current status: {req['status']}")
        
    updated_fields = {
        "status": "APPROVED",
        "approvedBy": ObjectId(reviewer["id"]),
        "approvedByName": reviewer.get("username", reviewer.get("email")),
        "approvedAt": datetime.datetime.utcnow(),
        "approvalRemarks": comments,
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.asset_requests.update_one({"_id": req_id_obj}, {"$set": updated_fields})
    updated_req = db.asset_requests.find_one({"_id": req_id_obj})
    
    old_val, new_val = get_dict_diff(req, updated_req)
    log_audit(
        action="request_approved",
        details=f"Asset Request {req['requestCode']} approved by {reviewer.get('email')}",
        performed_by_id=reviewer["id"],
        performed_by_email=reviewer["email"],
        entity_type="asset_request",
        entity_id=request_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_asset_request(updated_req)

def reject_asset_request(request_id_str, reason, reviewer):
    req_id_obj = ObjectId(request_id_str)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")
        
    if req["status"] != "PENDING":
        raise ValueError(f"Cannot reject request in current status: {req['status']}")
        
    updated_fields = {
        "status": "REJECTED",
        "rejectionReason": reason,
        "approvedBy": ObjectId(reviewer["id"]),
        "approvedByName": reviewer.get("username", reviewer.get("email")),
        "approvedAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.asset_requests.update_one({"_id": req_id_obj}, {"$set": updated_fields})
    updated_req = db.asset_requests.find_one({"_id": req_id_obj})
    
    old_val, new_val = get_dict_diff(req, updated_req)
    log_audit(
        action="request_rejected",
        details=f"Asset Request {req['requestCode']} rejected by {reviewer.get('email')}",
        performed_by_id=reviewer["id"],
        performed_by_email=reviewer["email"],
        entity_type="asset_request",
        entity_id=request_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_asset_request(updated_req)

def cancel_asset_request(request_id_str, user_id):
    req_id_obj = ObjectId(request_id_str)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")
        
    if req.get("employeeId") != str(user_id):
        raise PermissionError("Only the creator can cancel this request")
        
    if req["status"] != "PENDING":
        raise ValueError(f"Cannot cancel request in current status: {req['status']}")
        
    updated_fields = {
        "status": "CANCELLED",
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.asset_requests.update_one({"_id": req_id_obj}, {"$set": updated_fields})
    updated_req = db.asset_requests.find_one({"_id": req_id_obj})
    
    old_val, new_val = get_dict_diff(req, updated_req)
    log_audit(
        action="request_cancelled",
        details=f"Asset Request {req['requestCode']} cancelled by requester",
        performed_by_id=user_id,
        performed_by_email=req["employeeEmail"],
        entity_type="asset_request",
        entity_id=request_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_asset_request(updated_req)

def fulfill_asset_request(request_id_str, transaction_ids, fulfiller_user):
    req_id_obj = ObjectId(request_id_str)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")
        
    if req["status"] != "APPROVED":
        raise ValueError(f"Cannot fulfill request in current status: {req['status']}")
        
    tx_ids_objs = [ObjectId(tid) for tid in transaction_ids if tid]
    
    updated_fields = {
        "status": "FULFILLED",
        "fulfilledBy": ObjectId(fulfiller_user["id"]),
        "fulfilledAt": datetime.datetime.utcnow(),
        "linkedTransactionIds": tx_ids_objs,
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.asset_requests.update_one({"_id": req_id_obj}, {"$set": updated_fields})
    updated_req = db.asset_requests.find_one({"_id": req_id_obj})
    
    old_val, new_val = get_dict_diff(req, updated_req)
    log_audit(
        action="request_fulfilled",
        details=f"Asset Request {req['requestCode']} fulfilled by {fulfiller_user.get('email')}",
        performed_by_id=fulfiller_user["id"],
        performed_by_email=fulfiller_user["email"],
        entity_type="asset_request",
        entity_id=request_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_asset_request(updated_req)
