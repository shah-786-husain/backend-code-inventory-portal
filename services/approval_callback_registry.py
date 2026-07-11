import datetime
from bson import ObjectId
from utils.db import db
from services.notification_service import create_notification
from services.audit_service import log_audit

_CALLBACKS = {}

def register_callback(target_type, status, handler):
    """Registers a handler for a target type and status combination."""
    if target_type not in _CALLBACKS:
        _CALLBACKS[target_type] = {}
    _CALLBACKS[target_type][status] = handler

def trigger_callback(target_type, status, target_id, reviewer, comments, custom_data=None):
    """Triggers the registered handler for the event."""
    handler = _CALLBACKS.get(target_type, {}).get(status)
    if handler:
        try:
            return handler(target_id, reviewer, comments, custom_data)
        except Exception as e:
            print(f"Error in approval callback {target_type}.{status}: {e}")
            raise e
    return None

# Helper callback implementations for Asset Requests

def handle_asset_request_approved(target_id, reviewer, comments, custom_data):
    """Fires when the asset request is fully approved (final stage signoff)."""
    req_id_obj = ObjectId(target_id)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")

    updated_items = list(req.get("items", []))
    transactions_logged = []
    
    # Extract item allocations from custom_data (e.g., list of { index: int, allocatedItemCode: str })
    item_allocations = (custom_data or {}).get("items", [])
    alloc_map = {int(x.get("index")): x.get("allocatedItemCode") for x in item_allocations}
    
    for idx, item in enumerate(updated_items):
        allocated_code = alloc_map.get(idx)
        if not allocated_code:
            raise ValueError(f"Missing stock allocation for item at index {idx} ({item.get('itemName')})")
            
        inv_item = db.items.find_one({"itemCode": allocated_code})
        if not inv_item:
            raise ValueError(f"Inventory item {allocated_code} not found")
            
        qty_req = item.get("quantity", 1)
        qty_avail = inv_item.get("availableQuantity", 0)
        if qty_avail < qty_req:
            raise ValueError(f"Insufficient stock for {allocated_code}. Available: {qty_avail}, Requested: {qty_req}")
            
        # Bind item code to request
        item["allocatedItemCode"] = allocated_code
        
        # Decrement inventory quantity
        new_qty = max(0, qty_avail - qty_req)
        new_item_status = inv_item.get("status")
        if new_qty == 0:
            new_item_status = "out_of_stock"
        elif new_qty <= inv_item.get("minLimits", 0):
            new_item_status = "low_stock"
            
        db.items.update_one(
            {"_id": inv_item["_id"]},
            {
                "$set": {
                    "availableQuantity": new_qty,
                    "status": new_item_status,
                    "updatedAt": datetime.datetime.utcnow()
                }
            }
        )
        
        # Log transaction ledger
        tx_doc = {
            "transactionType": "issue",
            "itemCode": allocated_code,
            "quantity": qty_req,
            "issuedTo": req["requestedByUsername"],
            "actionBy": reviewer.get("email"),
            "remarks": f"Issued via generic request approval workflow {req['requestId']}",
            "timestamp": datetime.datetime.utcnow()
        }
        tx_res = db.transactions.insert_one(tx_doc)
        transactions_logged.append(tx_res.inserted_id)

    # Update request document status and links
    db.asset_requests.update_one(
        {"_id": req_id_obj},
        {
            "$set": {
                "status": "approved",
                "items": updated_items,
                "requestedItems": updated_items,
                "linkedTransactionId": transactions_logged[0] if transactions_logged else None,
                "linkedTransactionIds": transactions_logged,
                "approvedBy": ObjectId(reviewer["id"]) if reviewer.get("id") else None,
                "approvedByName": reviewer.get("username", reviewer.get("email")),
                "approvalRemarks": comments,
                "approvedAt": datetime.datetime.utcnow(),
                "updatedAt": datetime.datetime.utcnow()
            }
        }
    )

    # Notify requester
    create_notification(
        req["requestedBy"],
        f"Your request {req['requestId']} has been approved and assets allocated!",
        "request_approved",
        "/requests/my"
    )

    # Log Audit
    log_audit(
        "request_approved",
        f"Request {req['requestId']} fully approved & assets issued by {reviewer.get('email')}",
        reviewer.get("id"),
        reviewer.get("email"),
        "request",
        str(req["_id"]),
        {"status": req.get("status")},
        {"status": "approved"}
    )

def handle_asset_request_rejected(target_id, reviewer, comments, custom_data):
    """Fires when the asset request is rejected at any stage."""
    req_id_obj = ObjectId(target_id)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")

    db.asset_requests.update_one(
        {"_id": req_id_obj},
        {
            "$set": {
                "status": "rejected",
                "rejectionReason": comments,
                "approvedBy": ObjectId(reviewer["id"]) if reviewer.get("id") else None,
                "approvedByName": reviewer.get("username", reviewer.get("email")),
                "updatedAt": datetime.datetime.utcnow()
            }
        }
    )

    # Notify requester
    create_notification(
        req["requestedBy"],
        f"Your request {req['requestId']} has been rejected by {reviewer.get('email')}.",
        "request_rejected",
        "/requests/my"
    )

    # Log Audit
    log_audit(
        "request_rejected",
        f"Request {req['requestId']} rejected by {reviewer.get('email')}",
        reviewer.get("id"),
        reviewer.get("email"),
        "request",
        str(req["_id"]),
        {"status": req.get("status")},
        {"status": "rejected"}
    )

def handle_asset_request_sent_back(target_id, reviewer, comments, custom_data):
    """Fires when the asset request is sent back to the creator for modifications."""
    req_id_obj = ObjectId(target_id)
    req = db.asset_requests.find_one({"_id": req_id_obj})
    if not req:
        raise ValueError("Asset Request not found")

    db.asset_requests.update_one(
        {"_id": req_id_obj},
        {
            "$set": {
                "status": "sent_back",
                "rejectionReason": comments,
                "updatedAt": datetime.datetime.utcnow()
            }
        }
    )

    # Notify requester
    create_notification(
        req["requestedBy"],
        f"Your request {req['requestId']} was sent back by {reviewer.get('email')}. Remarks: {comments}",
        "request_sent_back",
        "/requests/my"
    )

    # Log Audit
    log_audit(
        "request_sent_back",
        f"Request {req['requestId']} sent back by {reviewer.get('email')}",
        reviewer.get("id"),
        reviewer.get("email"),
        "request",
        str(req["_id"]),
        {"status": req.get("status")},
        {"status": "sent_back"}
    )

# Generic handler factory for arbitrary target collections (e.g. purchase_order, transfer, maintenance_request)
def make_generic_status_callback(target_type, status_value):
    def callback_func(target_id, reviewer, comments, custom_data=None):
        target_id_obj = ObjectId(target_id)
        collection_name = target_type + "s" if not target_type.endswith("s") else target_type
        
        doc = db[collection_name].find_one({"_id": target_id_obj})
        if not doc:
            print(f"Generic callback: Target document {target_type} with ID {target_id} not found in {collection_name}")
            return
            
        db[collection_name].update_one(
            {"_id": target_id_obj},
            {"$set": {"status": status_value, "updatedAt": datetime.datetime.utcnow()}}
        )
        
        requester_id = doc.get("requesterId") or doc.get("requestedBy")
        if requester_id:
            create_notification(
                requester_id,
                f"Your {target_type.replace('_', ' ')} has been {status_value} by {reviewer.get('email')}.",
                f"{target_type}_{status_value}",
                f"/{target_type}s/my"
            )
            
        log_audit(
            f"{target_type}_{status_value}",
            f"{target_type.replace('_', ' ').capitalize()} updated to {status_value} by {reviewer.get('email')}",
            reviewer.get("id"),
            reviewer.get("email"),
            target_type,
            str(target_id_obj),
            {"status": doc.get("status")},
            {"status": status_value}
        )
    return callback_func

# Register callbacks
register_callback("asset_request", "approved", handle_asset_request_approved)
register_callback("asset_request", "rejected", handle_asset_request_rejected)
register_callback("asset_request", "sent_back", handle_asset_request_sent_back)

for t_type in ["purchase_order", "transfer", "maintenance_request"]:
    register_callback(t_type, "approved", make_generic_status_callback(t_type, "approved"))
    register_callback(t_type, "rejected", make_generic_status_callback(t_type, "rejected"))
    register_callback(t_type, "sent_back", make_generic_status_callback(t_type, "sent_back"))
