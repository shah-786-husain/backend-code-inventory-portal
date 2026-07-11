from datetime import datetime, timedelta
from bson import ObjectId
from utils.db import db

def create_notification(user_id, message, type_, link=None, recipient_role=None):
    """Creates a notification in-app for a specific user ID or recipient role."""
    try:
        doc = {
            "message": message,
            "type": type_,
            "link": link,
            "createdAt": datetime.utcnow()
        }
        if user_id:
            doc["userId"] = ObjectId(user_id) if isinstance(user_id, str) else user_id
            doc["read"] = False
            doc["archived"] = False
        if recipient_role:
            doc["recipientRole"] = recipient_role
            doc["readBy"] = []
            doc["archivedBy"] = []
            
        db.notifications.insert_one(doc)
    except Exception as e:
        print(f"Failed to create notification: {e}")

def list_notifications(user_id, role=None, read_only=None, include_archived=False):
    """Lists notifications targeting a specific user ID or role."""
    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    
    or_clauses = [
        {"userId": u_id}
    ]
    if role:
        or_clauses.append({"recipientRole": role})
        
    query = {"$or": or_clauses}
    
    docs = list(db.notifications.find(query).sort("createdAt", -1).limit(100))
    
    formatted = []
    for d in docs:
        is_role = "recipientRole" in d
        
        # Check read status
        is_read = d.get("read", False) if not is_role else (u_id in d.get("readBy", []))
        # Check archived status
        is_archived = d.get("archived", False) if not is_role else (u_id in d.get("archivedBy", []))
        
        # Filters
        if read_only is not None and is_read != read_only:
            continue
        if not include_archived and is_archived:
            continue
            
        formatted.append({
            "id": str(d["_id"]),
            "userId": str(d["userId"]) if "userId" in d else None,
            "recipientRole": d.get("recipientRole"),
            "message": d["message"],
            "type": d["type"],
            "link": d.get("link"),
            "read": is_read,
            "archived": is_archived,
            "createdAt": d["createdAt"].isoformat() if d.get("createdAt") else ""
        })
    return formatted

def mark_as_read(notification_id, user_id, role=None):
    """Marks a single notification as read."""
    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    notif_id = ObjectId(notification_id) if isinstance(notification_id, str) else notification_id
    
    d = db.notifications.find_one({"_id": notif_id})
    if not d:
        raise ValueError("Notification not found")
        
    if "userId" in d:
        if str(d["userId"]) != str(u_id):
            raise PermissionError("Unauthorized to modify this notification")
        db.notifications.update_one(
            {"_id": notif_id},
            {"$set": {"read": True}}
        )
    elif "recipientRole" in d:
        if d["recipientRole"] != role:
            raise PermissionError("Unauthorized to modify this notification")
        db.notifications.update_one(
            {"_id": notif_id},
            {"$addToSet": {"readBy": u_id}}
        )

def archive_notification(notification_id, user_id, role=None):
    """Archives a single notification."""
    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    notif_id = ObjectId(notification_id) if isinstance(notification_id, str) else notification_id
    
    d = db.notifications.find_one({"_id": notif_id})
    if not d:
        raise ValueError("Notification not found")
        
    if "userId" in d:
        if str(d["userId"]) != str(u_id):
            raise PermissionError("Unauthorized to modify this notification")
        db.notifications.update_one(
            {"_id": notif_id},
            {"$set": {"archived": True}}
        )
    elif "recipientRole" in d:
        if d["recipientRole"] != role:
            raise PermissionError("Unauthorized to modify this notification")
        db.notifications.update_one(
            {"_id": notif_id},
            {"$addToSet": {"archivedBy": u_id}}
        )

def mark_all_read(user_id, role=None):
    """Marks all active notifications targeting the user as read."""
    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    
    # 1. Update user-targeted unread notifications
    db.notifications.update_many(
        {"userId": u_id, "read": False},
        {"$set": {"read": True}}
    )
    
    # 2. Update role-targeted unread notifications
    if role:
        db.notifications.update_many(
            {"recipientRole": role, "readBy": {"$ne": u_id}},
            {"$addToSet": {"readBy": u_id}}
        )

def archive_all(user_id, role=None):
    """Archives all active notifications targeting the user."""
    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    
    # 1. Archive user-targeted notifications
    db.notifications.update_many(
        {"userId": u_id, "archived": False},
        {"$set": {"archived": True}}
    )
    
    # 2. Archive role-targeted notifications
    if role:
        db.notifications.update_many(
            {"recipientRole": role, "archivedBy": {"$ne": u_id}},
            {"$addToSet": {"archivedBy": u_id}}
        )

def check_overdue_returns():
    """Sweeps transactions and triggers overdue return notifications."""
    try:
        now = datetime.utcnow()
        # Find active issue transactions that are overdue (expectedReturnDate in past)
        overdue_issues = list(db.transactions.find({
            "transactionType": "issue",
            "expectedReturnDate": {"$lt": now}
        }))
        
        for tx in overdue_issues:
            user_email = tx.get("issuedTo")
            item_code = tx.get("itemCode")
            expected_date = tx.get("expectedReturnDate")
            
            if not user_email or not item_code or not expected_date:
                continue
                
            # Determine if this issue is still outstanding
            # Calculate returns for this item code by this user after the issue timestamp
            total_returned = 0
            return_txs = list(db.transactions.find({
                "transactionType": "return",
                "itemCode": item_code,
                "actionByEmail": user_email,
                "timestamp": {"$gt": tx["timestamp"]}
            }))
            for r in return_txs:
                total_returned += r.get("quantity", 0)
                
            issued_qty = tx.get("quantity", 0)
            outstanding = max(0, issued_qty - total_returned)
            
            if outstanding > 0:
                # Look up user to get their userId
                user = db.users.find_one({"email": user_email})
                if user:
                    # Find item name
                    item = db.items.find_one({"itemCode": item_code})
                    item_name = item.get("itemName", "Asset") if item else "Asset"
                    expected_date_str = expected_date.strftime("%Y-%m-%d")
                    
                    # 1. Notify the user
                    msg = f"Overdue return alert: Item '{item_name}' ({item_code}) was expected to be returned by {expected_date_str}."
                    existing_user_notif = db.notifications.find_one({
                        "userId": user["_id"],
                        "type": "overdue_return",
                        "link": f"/inventory/{item_code}"
                    })
                    if not existing_user_notif:
                        create_notification(
                            user_id=user["_id"],
                            message=msg,
                            type_="overdue_return",
                            link=f"/inventory/{item_code}"
                        )
                        
                    # 2. Notify store heads and admins
                    msg_role = f"Overdue return: {user_email} has not returned '{item_name}' ({item_code}) due on {expected_date_str}."
                    for role_name in ["store_head", "admin"]:
                        existing_role_notif = db.notifications.find_one({
                            "recipientRole": role_name,
                            "type": "overdue_return",
                            "link": f"/inventory/{item_code}"
                        })
                        if not existing_role_notif:
                            create_notification(
                                user_id=None,
                                message=msg_role,
                                type_="overdue_return",
                                link=f"/inventory/{item_code}",
                                recipient_role=role_name
                            )
    except Exception as e:
        print(f"Failed to sweep overdue returns: {e}")

def check_maintenance_reminders():
    """Sweeps scheduled maintenance tasks and triggers reminders."""
    try:
        now = datetime.utcnow()
        # Find scheduled maintenance logs
        tickets = list(db.maintenance_logs.find({
            "status": "scheduled"
        }))
        
        for ticket in tickets:
            sch_date_val = ticket.get("scheduledDate")
            if not sch_date_val:
                continue
                
            parsed_sch = None
            if isinstance(sch_date_val, str):
                try:
                    parsed_sch = datetime.fromisoformat(sch_date_val.replace('Z', '+00:00')).replace(tzinfo=None)
                except Exception:
                    pass
            elif isinstance(sch_date_val, datetime):
                parsed_sch = sch_date_val.replace(tzinfo=None)
                
            if not parsed_sch:
                continue
                
            # Trigger reminder if scheduledDate is in the past, or due within next 24 hours
            if parsed_sch <= now + timedelta(days=1):
                mnt_id = ticket.get("maintenanceId")
                item_code = ticket.get("itemCode")
                msg = f"Maintenance reminder: Ticket {mnt_id} for asset {item_code} is scheduled for {parsed_sch.strftime('%Y-%m-%d')}."
                
                for role_name in ["store_head", "admin"]:
                    existing = db.notifications.find_one({
                        "recipientRole": role_name,
                        "type": "maintenance_reminder",
                        "link": f"/maintenance?ticket={mnt_id}"
                    })
                    if not existing:
                        create_notification(
                            user_id=None,
                            message=msg,
                            type_="maintenance_reminder",
                            link=f"/maintenance?ticket={mnt_id}",
                            recipient_role=role_name
                        )
    except Exception as e:
        print(f"Failed to sweep maintenance reminders: {e}")
