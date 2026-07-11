from datetime import datetime
from utils.db import db

def seed_default_policies():
    """Seeds initial system default policies if none exist."""
    if db.approval_policies.count_documents({}) > 0:
        return

    default_policies = [
        {
            "policyCode": "POL-ASSET-REQ",
            "targetType": "asset_request",
            "description": "Standard approval workflow for employee hardware asset requests",
            "isActive": True,
            "rules": [
                {
                    "ruleName": "Employee Asset Allocation Request",
                    "condition": "True",  # Always applies as catch-all
                    "steps": [
                        {
                            "stepIndex": 0,
                            "stepName": "Manager Review",
                            "requiredRoles": ["manager"],
                            "actionType": "single_signoff"
                        },
                        {
                            "stepIndex": 1,
                            "stepName": "Store Head Allocation",
                            "requiredRoles": ["store_head", "admin"],
                            "actionType": "single_signoff"
                        }
                    ]
                }
            ],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        },
        {
            "policyCode": "POL-PURCHASE-ORD",
            "targetType": "purchase_order",
            "description": "Approval workflow for procurement invoices and purchase orders",
            "isActive": True,
            "rules": [
                {
                    "ruleName": "High Value Procurement",
                    "condition": "float(totalAmount) > 50000",
                    "steps": [
                        {
                            "stepIndex": 0,
                            "stepName": "Store Head Verification",
                            "requiredRoles": ["store_head"],
                            "actionType": "single_signoff"
                        },
                        {
                            "stepIndex": 1,
                            "stepName": "Admin Approval Signoff",
                            "requiredRoles": ["admin"],
                            "actionType": "single_signoff"
                        }
                    ]
                },
                {
                    "ruleName": "Standard Procurement Review",
                    "condition": "float(totalAmount) <= 50000",
                    "steps": [
                        {
                            "stepIndex": 0,
                            "stepName": "Store Head Review",
                            "requiredRoles": ["store_head", "admin"],
                            "actionType": "single_signoff"
                        }
                    ]
                }
            ],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
    ]

    db.approval_policies.insert_many(default_policies)

def evaluate_policy_steps(target_type, target_entity):
    """
    Evaluates policy rules for a target type and entity instance.
    Returns the steps list corresponding to the matching rule.
    """
    # Seed default policies first to guarantee existence
    seed_default_policies()

    policy = db.approval_policies.find_one({"targetType": target_type, "isActive": True})
    if not policy:
        return []

    # Evaluate each rule condition in order
    for rule in policy.get("rules", []):
        condition = rule.get("condition", "True")
        try:
            # Evaluate using local environment containing target fields
            # We convert dict keys to local variables for convenient evaluation
            context = dict(target_entity)
            if eval(condition, {"__builtins__": None, "float": float, "int": int, "str": str, "bool": bool}, context):
                return rule.get("steps", [])
        except Exception as e:
            # Fallback in case of parsing errors: check next rule or log
            print(f"Error evaluating rule condition '{condition}': {e}")
            continue

    return []
