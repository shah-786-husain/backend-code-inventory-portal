import datetime
from bson import ObjectId
from utils.db import db
from services.approval_policy_service import evaluate_policy_steps
from services.approval_callback_registry import trigger_callback
from services.notification_service import create_notification
from services.audit_service import log_audit

def submit_to_approvals(target_type, target_id_str, summary_snapshot, requester_id_str, requester_username):
    """
    Submits a target document into the generic approval engine.
    Resolves policy rules and spawns runtime steps.
    """
    # Fetch target details from appropriate collection for evaluation context
    target_id_obj = ObjectId(target_id_str)
    target_collection = db[target_type + "s"] if not target_type.endswith("s") else db[target_type]
    target_doc = target_collection.find_one({"_id": target_id_obj})
    if not target_doc:
        raise ValueError(f"Target document {target_type} with ID {target_id_str} not found")

    # Evaluate dynamic steps from active policies
    steps_definition = evaluate_policy_steps(target_type, target_doc)
    if not steps_definition:
        # Default fallback step if policy is missing or evaluates empty
        steps_definition = [
            {
                "stepIndex": 0,
                "stepName": "Standard Verification",
                "requiredRoles": ["admin", "store_head"],
                "actionType": "single_signoff"
            }
        ]

    # Calculate sequential sequential approval ID: e.g., APR-202607-0001
    current_month = datetime.datetime.utcnow().strftime("%Y%m")
    prefix = f"APR-{current_month}-"
    count = db.approval_requests.count_documents({"approvalId": {"$regex": f"^{prefix}"}})
    approval_id = f"{prefix}{str(count + 1).zfill(4)}"

    # Setup steps runtime records
    runtime_steps = []
    for s in steps_definition:
        runtime_steps.append({
            "stepIndex": s.get("stepIndex", 0),
            "stepName": s.get("stepName", "Review Step"),
            "requiredRoles": s.get("requiredRoles", []),
            "status": "pending",
            "reviewedBy": None,
            "reviewedByUsername": None,
            "reviewedAt": None,
            "comments": ""
        })

    approval_request = {
        "approvalId": approval_id,
        "targetType": target_type,
        "targetId": target_id_obj,
        "requesterId": ObjectId(requester_id_str),
        "requesterUsername": requester_username,
        "status": "pending",
        "currentStepIndex": 0,
        "steps": runtime_steps,
        "summarySnapshot": summary_snapshot,
        "history": [
            {
                "action": "submitted",
                "stepIndex": None,
                "operatorId": ObjectId(requester_id_str),
                "operatorUsername": requester_username,
                "comments": "Initiated approval request",
                "timestamp": datetime.datetime.utcnow()
            }
        ],
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }

    db.approval_requests.insert_one(approval_request)

    # Notify next reviewers
    notify_next_reviewers(approval_request)

    # Update actual target status to pending manager/store_head
    first_step_roles = runtime_steps[0]["requiredRoles"]
    target_status = "pending_manager" if "manager" in first_step_roles else "pending_store_head"
    target_collection.update_one({"_id": target_id_obj}, {"$set": {"status": target_status}})

    return approval_id

def process_step_action(approval_id_str, action, comments, reviewer, custom_data=None):
    """
    Processes an approval step action (approve, reject, send_back).
    Triggers observers when final state is resolved.
    """
    req = db.approval_requests.find_one({"approvalId": approval_id_str})
    if not req:
        raise ValueError(f"Approval request {approval_id_str} not found")

    if req["status"] not in ["pending", "sent_back"]:
        raise ValueError(f"Approval request status '{req['status']}' cannot be modified")

    current_idx = req["currentStepIndex"]
    steps = req["steps"]
    
    if current_idx >= len(steps):
        raise ValueError("Invalid approval state: current step index out of bounds")

    active_step = steps[current_idx]
    reviewer_role = reviewer.get("role")
    reviewer_id = ObjectId(reviewer.get("id"))
    reviewer_email = reviewer.get("email")

    # Authorize reviewer role
    if reviewer_role not in active_step["requiredRoles"] and reviewer_role != "admin":
        raise ValueError(f"Role '{reviewer_role}' is not authorized to sign off this step")

    # Perform action transitions
    history_entry = {
        "stepIndex": current_idx,
        "operatorId": reviewer_id,
        "operatorUsername": reviewer_email,
        "comments": comments,
        "timestamp": datetime.datetime.utcnow()
    }

    target_type = req["targetType"]
    target_id = req["targetId"]

    target_collection = db[target_type + "s"] if not target_type.endswith("s") else db[target_type]

    if action == "reject":
        # Final rejection
        active_step["status"] = "rejected"
        active_step["reviewedBy"] = reviewer_id
        active_step["reviewedByUsername"] = reviewer_email
        active_step["reviewedAt"] = datetime.datetime.utcnow()
        active_step["comments"] = comments

        req["status"] = "rejected"
        history_entry["action"] = "rejected"
        req["history"].append(history_entry)

        db.approval_requests.update_one(
            {"_id": req["_id"]},
            {
                "$set": {
                    "status": "rejected",
                    "steps": steps,
                    "history": req["history"],
                    "updatedAt": datetime.datetime.utcnow()
                }
            }
        )

        # Trigger rejection callbacks
        trigger_callback(target_type, "rejected", target_id, reviewer, comments, custom_data)
        return "rejected"

    elif action == "send_back":
        # Send back to creator
        active_step["status"] = "sent_back"
        active_step["reviewedBy"] = reviewer_id
        active_step["reviewedByUsername"] = reviewer_email
        active_step["reviewedAt"] = datetime.datetime.utcnow()
        active_step["comments"] = comments

        req["status"] = "sent_back"
        history_entry["action"] = "sent_back"
        req["history"].append(history_entry)

        db.approval_requests.update_one(
            {"_id": req["_id"]},
            {
                "$set": {
                    "status": "sent_back",
                    "steps": steps,
                    "history": req["history"],
                    "updatedAt": datetime.datetime.utcnow()
                }
            }
        )

        # Trigger send_back callbacks
        trigger_callback(target_type, "sent_back", target_id, reviewer, comments, custom_data)
        return "sent_back"

    elif action == "approve":
        # Sign off step
        active_step["status"] = "approved"
        active_step["reviewedBy"] = reviewer_id
        active_step["reviewedByUsername"] = reviewer_email
        active_step["reviewedAt"] = datetime.datetime.utcnow()
        active_step["comments"] = comments

        history_entry["action"] = "approved_step"
        req["history"].append(history_entry)

        # Evaluate if workflow is completed
        if current_idx + 1 < len(steps):
            # Advance to next step
            req["currentStepIndex"] = current_idx + 1
            next_roles = steps[current_idx + 1]["requiredRoles"]
            next_status = "pending_manager" if "manager" in next_roles else "pending_store_head"
            
            db.approval_requests.update_one(
                {"_id": req["_id"]},
                {
                    "$set": {
                        "currentStepIndex": current_idx + 1,
                        "steps": steps,
                        "history": req["history"],
                        "updatedAt": datetime.datetime.utcnow()
                    }
                }
            )
            # Update target doc status to match next step
            target_collection.update_one({"_id": target_id}, {"$set": {"status": next_status}})
            
            # Notify next step reviewers
            notify_next_reviewers(req)
            return "pending"
        else:
            # Final approval signoff!
            req["status"] = "approved"
            db.approval_requests.update_one(
                {"_id": req["_id"]},
                {
                    "$set": {
                        "status": "approved",
                        "steps": steps,
                        "history": req["history"],
                        "updatedAt": datetime.datetime.utcnow()
                    }
                }
            )

            # Trigger successful approval observer
            trigger_callback(target_type, "approved", target_id, reviewer, comments, custom_data)
            return "approved"

    raise ValueError(f"Unsupported workflow action '{action}'")

def notify_next_reviewers(approval_req):
    """Dispatches in-app alert notifications to target reviewers for the current active step."""
    current_idx = approval_req["currentStepIndex"]
    active_step = approval_req["steps"][current_idx]
    roles = active_step.get("requiredRoles", [])
    step_name = active_step.get("stepName", "Review")
    
    users = list(db.users.find({"role": {"$in": roles}}))
    msg = f"New approval task for {approval_req['summarySnapshot'].get('title')} requires {step_name}."
    
    for u in users:
        create_notification(
            u["_id"],
            msg,
            "request_alert",
            "/requests/pending"
        )

def list_pending_reviews(user, status_filter="pending", target_type_filter=None):
    """Lists requests that match status and target filters, scoped to the user's role and history."""
    role = user.get("role")
    user_id = ObjectId(user.get("id"))
    
    query = {}
    if status_filter:
        query["status"] = status_filter
    if target_type_filter:
        query["targetType"] = target_type_filter
        
    all_matching = list(db.approval_requests.find(query).sort("createdAt", -1))
    
    filtered = []
    for req in all_matching:
        if req["status"] == "pending":
            idx = req["currentStepIndex"]
            if idx < len(req["steps"]):
                active_step = req["steps"][idx]
                if role in active_step["requiredRoles"] or role == "admin":
                    # Special manager filter: manager only reviews requests belonging to users in their department
                    if role == "manager" and role != "admin":
                        dept_users = list(db.users.find({"department": user.get("department")}, {"_id": 1}))
                        dept_ids = [u["_id"] for u in dept_users]
                        if req["requesterId"] not in dept_ids:
                            continue  # Not in department
                    filtered.append(serialize_approval(req))
        else:
            # For non-pending (approved/rejected/sent_back), show if admin/store_head, or if they requested it,
            # or if they signed off on any step.
            if role in ["admin", "store_head"] or str(req["requesterId"]) == str(user_id):
                filtered.append(serialize_approval(req))
            else:
                involved = False
                for step in req.get("steps", []):
                    if step.get("reviewedBy") and str(step["reviewedBy"]) == str(user_id):
                        involved = True
                        break
                if involved:
                    filtered.append(serialize_approval(req))
                
    return filtered

def list_user_submissions(user_id_str):
    """Lists approval requests submitted by the logged-in user."""
    uid = ObjectId(user_id_str)
    docs = list(db.approval_requests.find({"requesterId": uid}).sort("createdAt", -1))
    return [serialize_approval(d) for d in docs]

def get_approval_details(approval_id_str):
    """Retrieves full approval details with steps and history."""
    d = db.approval_requests.find_one({"approvalId": approval_id_str})
    return serialize_approval(d)

def serialize_approval(d):
    """Helpers to convert ObjectIds and datetime to strings for JSON payload serialization."""
    if not d:
        return None
        
    def _format_date(val):
        if isinstance(val, datetime.datetime):
            return val.isoformat()
        return str(val) if val else ""

    return {
        "id": str(d["_id"]),
        "approvalId": d.get("approvalId"),
        "targetType": d.get("targetType"),
        "targetId": str(d.get("targetId")),
        "requesterId": str(d.get("requesterId")),
        "requesterUsername": d.get("requesterUsername"),
        "status": d.get("status"),
        "currentStepIndex": d.get("currentStepIndex", 0),
        "steps": [
            {
                "stepIndex": s["stepIndex"],
                "stepName": s["stepName"],
                "requiredRoles": s["requiredRoles"],
                "status": s["status"],
                "reviewedBy": str(s["reviewedBy"]) if s.get("reviewedBy") else None,
                "reviewedByUsername": s.get("reviewedByUsername"),
                "reviewedAt": _format_date(s.get("reviewedAt")),
                "comments": s.get("comments", "")
            }
            for s in d.get("steps", [])
        ],
        "summarySnapshot": d.get("summarySnapshot", {}),
        "history": [
            {
                "action": h["action"],
                "stepIndex": h.get("stepIndex"),
                "operatorId": str(h["operatorId"]),
                "operatorUsername": h["operatorUsername"],
                "comments": h.get("comments", ""),
                "timestamp": _format_date(h["timestamp"])
            }
            for h in d.get("history", [])
        ],
        "createdAt": _format_date(d.get("createdAt")),
        "updatedAt": _format_date(d.get("updatedAt"))
    }
