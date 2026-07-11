import datetime
from bson import ObjectId
from utils.db import get_db
from services.audit_log_service import log_audit

def _to_object_id(id_val):
    if not id_val:
        return None
    try:
        return ObjectId(id_val)
    except Exception:
        return id_val

def serialize_maintenance_ticket(t):
    if not t:
        return None
    db = get_db()
    
    # Extract item ID safely
    item_id_str = ""
    if t.get("itemId"):
        item_id_str = str(t.get("itemId"))
        
    item = None
    if item_id_str and ObjectId.is_valid(item_id_str):
        try:
            item = db.items.find_one({"_id": ObjectId(item_id_str)}, {"itemName": 1})
        except Exception:
            pass
            
    # Safely format dates
    def _format_date(val):
        if not val:
            return ""
        if isinstance(val, datetime.datetime):
            return val.isoformat()
        return str(val)

    return {
        "id": str(t.get("_id", "")),
        "maintenanceId": t.get("maintenanceId", ""),
        "itemId": item_id_str,
        "itemCode": t.get("itemCode", ""),
        "serialNumber": t.get("serialNumber", ""),
        "maintenanceType": t.get("maintenanceType", ""),
        "status": t.get("status", ""),
        "title": t.get("title", ""),
        "details": t.get("details", ""),
        "vendor": t.get("vendor", ""),
        "cost": float(t.get("cost") or 0.0),
        "warrantyCovered": bool(t.get("warrantyCovered", False)),
        "scheduledDate": _format_date(t.get("scheduledDate")),
        "startDate": _format_date(t.get("startDate")),
        "endDate": _format_date(t.get("endDate")),
        "performedBy": t.get("performedBy", ""),
        "nextServiceDate": _format_date(t.get("nextServiceDate")),
        "createdAt": _format_date(t.get("createdAt")),
        "updatedAt": _format_date(t.get("updatedAt")),
        "itemName": item["itemName"] if item else "Unknown Asset"
    }

def schedule_maintenance(data, operator):
    """
    Schedule a maintenance/calibration/repair ticket for an asset.
    """
    db = get_db()
    item_code = data.get('itemCode', '').strip()
    item = db.items.find_one({"itemCode": item_code})
    if not item:
        raise ValueError(f"Asset with item code '{item_code}' not found.")

    # Generate sequential maintenanceId (MNT-YYYYMM-XXXX)
    now = datetime.datetime.utcnow()
    prefix = f"MNT-{now.strftime('%Y%m')}-"
    count = db.maintenance_logs.count_documents({"maintenanceId": {"$regex": f"^{prefix}"}})
    mnt_id = f"{prefix}{count + 1:04d}"

    ticket = {
        "maintenanceId": mnt_id,
        "itemId": item["_id"],
        "itemCode": item_code,
        "serialNumber": data.get("serialNumber") or item.get("serialNumber") or "",
        "maintenanceType": data.get("maintenanceType", "scheduled"), # scheduled, breakdown, calibration, preventive
        "status": "scheduled", # scheduled, in_progress, completed, cancelled
        "title": data.get("title", "").strip(),
        "details": data.get("details", "").strip(),
        "vendor": data.get("vendor", "").strip(),
        "cost": float(data.get("cost") or 0.0),
        "warrantyCovered": bool(data.get("warrantyCovered", False)),
        "scheduledDate": data.get("scheduledDate") or now.isoformat(),
        "startDate": None,
        "endDate": None,
        "performedBy": operator.get("email", ""),
        "nextServiceDate": data.get("nextServiceDate"),
        "createdAt": now,
        "updatedAt": now
    }

    db.maintenance_logs.insert_one(ticket)

    # Automatically set the asset status to 'maintenance'
    db.items.update_one(
        {"_id": item["_id"]},
        {"$set": {"status": "maintenance"}}
    )

    # Log transition transaction history
    tx = {
        'transactionType': 'repair',
        'itemCode': item_code,
        'quantity': 1,
        'actionBy': _to_object_id(operator.get("id")),
        'actionByEmail': operator.get("email"),
        'remarks': f"Maintenance scheduled: {ticket['title']}. Ticket ID: {mnt_id}",
        'timestamp': now
    }
    db.transactions.insert_one(tx)

    # Audit log
    log_audit(
        action='stock_adjusted',
        details=f"Scheduled maintenance '{ticket['title']}' ({mnt_id}) for '{item_code}'",
        performed_by_id=_to_object_id(operator.get("id")),
        performed_by_email=operator.get("email"),
        entity_type="item",
        entity_id=item["_id"]
    )

    return serialize_maintenance_ticket(ticket)

def update_maintenance_status(mnt_id, data, operator):
    """
    Update ticket status, cost, or comments, and manage item lifecycle transition.
    """
    db = get_db()
    ticket = db.maintenance_logs.find_one({"maintenanceId": mnt_id})
    if not ticket:
        raise ValueError(f"Maintenance ticket '{mnt_id}' not found.")

    new_status = data.get("status")
    cost = float(data.get("cost") or ticket.get("cost", 0.0))
    details = data.get("details") or ticket.get("details", "")
    now = datetime.datetime.utcnow()

    update_fields = {
        "status": new_status,
        "cost": cost,
        "details": details,
        "updatedAt": now
    }

    if new_status == "in_progress" and not ticket.get("startDate"):
        update_fields["startDate"] = now.isoformat()
    elif new_status in ["completed", "cancelled"]:
        update_fields["endDate"] = now.isoformat()

    db.maintenance_logs.update_one(
        {"_id": ticket["_id"]},
        {"$set": update_fields}
    )

    # Manage item status transition if ticket was closed
    item = db.items.find_one({"_id": ticket["itemId"]})
    if item:
        target_status = None
        if new_status == "completed":
            target_status = "available"
        elif new_status == "cancelled":
            # Revert to available
            target_status = "available"

        if target_status:
            db.items.update_one(
                {"_id": item["_id"]},
                {"$set": {"status": target_status}}
            )

            # Insert transition log
            tx = {
                'transactionType': 'adjust',
                'itemCode': item["itemCode"],
                'quantity': 1,
                'actionBy': _to_object_id(operator.get("id")),
                'actionByEmail': operator.get("email"),
                'remarks': f"Maintenance ticket {mnt_id} marked {new_status}. Asset returned to inventory.",
                'timestamp': now
            }
            db.transactions.insert_one(tx)

    # Audit log
    log_audit(
        action='stock_adjusted',
        details=f"Updated maintenance ticket '{mnt_id}' status to '{new_status}'",
        performed_by_id=_to_object_id(operator.get("id")),
        performed_by_email=operator.get("email"),
        entity_type="item",
        entity_id=ticket["itemId"]
    )

    updated_ticket = db.maintenance_logs.find_one({"_id": ticket["_id"]})
    return serialize_maintenance_ticket(updated_ticket)

def list_tickets(filters=None):
    """
    List all maintenance service records, merging name from items list.
    """
    db = get_db()
    query = {}
    if filters:
        if filters.get("itemCode"):
            query["itemCode"] = filters.get("itemCode")
        if filters.get("status"):
            query["status"] = filters.get("status")
        if filters.get("maintenanceType"):
            query["maintenanceType"] = filters.get("maintenanceType")

    tickets = list(db.maintenance_logs.find(query).sort("createdAt", -1))
    return [serialize_maintenance_ticket(t) for t in tickets]

def decommission_asset(item_code, data, operator):
    """
    Decommission/dispose an asset permanently from the system.
    """
    db = get_db()
    item = db.items.find_one({"itemCode": item_code})
    if not item:
        raise ValueError(f"Asset with item code '{item_code}' not found.")

    disposal_method = data.get("disposalMethod", "scrapped") # scrapped, sold, recycled
    salvage_value = float(data.get("salvageValue") or 0.0)
    remarks = data.get("remarks", "").strip()
    now = datetime.datetime.utcnow()

    # Update item attributes
    update_doc = {
        "status": "disposed",
        "disposalMethod": disposal_method,
        "disposalDate": now,
        "disposalValue": salvage_value,
        "remarks": remarks
    }

    db.items.update_one(
        {"_id": item["_id"]},
        {"$set": update_doc}
    )

    # Insert EOL ledger transaction
    tx = {
        'transactionType': 'adjust',
        'itemCode': item_code,
        'quantity': item.get("quantity", 1),
        'actionBy': _to_object_id(operator.get("id")),
        'actionByEmail': operator.get("email"),
        'remarks': f"DECOMMISSIONED via {disposal_method.upper()}. Salvage: ₹{salvage_value:.2f}. Notes: {remarks}",
        'timestamp': now
    }
    db.transactions.insert_one(tx)

    # Audit log
    log_audit(
        action='item_deleted',
        details=f"Decommissioned asset '{item_code}' via '{disposal_method}'",
        performed_by_id=_to_object_id(operator.get("id")),
        performed_by_email=operator.get("email"),
        entity_type="item",
        entity_id=item["_id"]
    )

    from services.item_service import serialize_item
    updated_item = db.items.find_one({"_id": item["_id"]})
    return serialize_item(updated_item)
