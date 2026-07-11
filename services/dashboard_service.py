"""
Dashboard Service — Phase 2

Aggregates real data from items, invoices, transactions, and users
collections using consolidated $facet pipelines. Provides role-aware
response filtering, handles empty collections gracefully, and supports in-memory TTL caching.
"""

import os
import time
from datetime import datetime, timedelta
from utils.db import db

# ---------------------------------------------------------------------------
# In-memory TTL cache (per-role, no external dependency)
# ---------------------------------------------------------------------------
_cache = {}
_CACHE_TTL = int(os.environ.get('DASHBOARD_CACHE_TTL_SECONDS', 30))


def _get_cached(role, user_id=None):
    key = f"dashboard_{role}" if role != 'team_member' else f"dashboard_{user_id}"
    entry = _cache.get(key)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL:
        return entry['data']
    return None


def _set_cached(role, data, user_id=None):
    key = f"dashboard_{role}" if role != 'team_member' else f"dashboard_{user_id}"
    _cache[key] = {'data': data, 'ts': time.time()}


# ---------------------------------------------------------------------------
# Aggregation Pipelines
# ---------------------------------------------------------------------------

def _run_items_pipeline():
    """Single $facet call against the items collection."""
    pipeline = [
        {"$facet": {
            "totalItems": [{"$count": "count"}],

            "stockTotals": [
                {"$group": {
                    "_id": None,
                    "totalAvailable": {"$sum": "$availableQuantity"},
                    "totalIssued": {"$sum": "$issuedQuantity"},
                }}
            ],

            "lowStockItems": [
                {"$match": {
                    "availableQuantity": {"$gt": 0},
                    "$expr": {
                        "$lte": [
                            "$availableQuantity",
                            {"$ifNull": ["$reorderThreshold", {"$ifNull": ["$minQuantity", {"$ifNull": ["$minimumQuantity", 5]}]}]}
                        ]
                    }
                }},
                {"$count": "count"},
            ],

            "outOfStockItems": [
                {"$match": {"availableQuantity": {"$lte": 0}}},
                {"$count": "count"},
            ],

            "damagedItems": [
                {"$match": {"status": {"$in": ["Damaged", "damaged"]}}},
                {"$count": "count"},
            ],

            "categoryWiseStock": [
                {"$group": {
                    "_id": "$category",
                    "total": {"$sum": "$quantity"},
                    "available": {"$sum": "$availableQuantity"},
                    "issued": {"$sum": "$issuedQuantity"},
                }},
                {"$project": {
                    "category": "$_id", "_id": 0,
                    "total": 1, "available": 1, "issued": 1,
                }},
                {"$sort": {"total": -1}},
                {"$limit": 15},
            ],

            "statusWiseStock": [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                {"$project": {"status": "$_id", "_id": 0, "count": 1}},
                {"$sort": {"count": -1}},
            ],

            "lowStockRequiringPurchase": [
                {"$match": {
                    "$expr": {
                        "$lte": [
                            "$availableQuantity",
                            {"$ifNull": ["$reorderThreshold", {"$ifNull": ["$minQuantity", {"$ifNull": ["$minimumQuantity", 5]}]}]}
                        ]
                    }
                }},
                {"$project": {
                    "_id": 0,
                    "itemCode": 1, "itemName": 1,
                    "availableQuantity": 1,
                    "totalQuantity": "$quantity",
                    "category": 1,
                }},
                {"$limit": 10},
            ],

            "alertItems": [
                {"$match": {
                    "$expr": {
                        "$lte": [
                            "$availableQuantity",
                            {"$ifNull": ["$reorderThreshold", {"$ifNull": ["$minQuantity", {"$ifNull": ["$minimumQuantity", 5]}]}]}
                        ]
                    }
                }},
                {"$project": {
                    "_id": 0, "itemName": 1, "itemCode": 1,
                    "status": 1, "availableQuantity": 1,
                }},
                {"$limit": 8},
            ],
        }}
    ]
    try:
        result = list(db.items.aggregate(pipeline))
        return result[0] if result else {}
    except Exception:
        return {}


def _run_invoices_pipeline():
    """Single $facet call against the invoices collection."""
    pipeline = [
        {"$facet": {
            "invoiceTotals": [
                {"$group": {
                    "_id": None,
                    "totalInvoices": {"$sum": 1},
                    "totalPurchaseValue": {"$sum": "$totalAmount"},
                }}
            ],
        }}
    ]
    try:
        result = list(db.invoices.aggregate(pipeline))
        return result[0] if result else {}
    except Exception:
        return {}


def _run_transactions_pipeline(user_filter=None):
    """Single $facet call against the transactions collection.

    If *user_filter* is provided (email or username), the recent-transactions
    facet is scoped to that user only (for team_member role).
    """
    # Recent transactions sub-pipeline
    recent_match = [{"$sort": {"timestamp": -1}}]
    if user_filter:
        recent_match.insert(0, {"$match": {"issuedTo": user_filter}})
    recent_match += [
        {"$limit": 10},
        {"$lookup": {
            "from": "items",
            "localField": "itemCode",
            "foreignField": "itemCode",
            "as": "itemInfo",
        }},
        {"$project": {
            "id": {"$toString": "$_id"},
            "_id": 0,
            "transactionType": 1,
            "itemCode": 1,
            "itemName": {"$ifNull": [
                {"$arrayElemAt": ["$itemInfo.itemName", 0]},
                "Unknown Item",
            ]},
            "quantity": 1,
            "issuedTo": 1,
            "toLocation": 1,
            "fromLocation": 1,
            "remarks": 1,
            "timestamp": 1,
        }},
    ]

    pipeline = [
        {"$facet": {
            "recentTransactions": recent_match,

            # Issued items with no matching return (overdue candidates)
            "issuedNotReturned": [
                {"$match": {"transactionType": "issue"}},
                {"$sort": {"timestamp": -1}},
                {"$limit": 100},  # increased to allow better filtering
                {"$lookup": {
                    "from": "transactions",
                    "let": {"code": "$itemCode", "issued_to": "$issuedTo"},
                    "pipeline": [
                        {"$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$transactionType", "return"]},
                                    {"$eq": ["$itemCode", "$$code"]},
                                ]
                            }
                        }},
                        {"$sort": {"timestamp": -1}},
                        {"$limit": 1},
                    ],
                    "as": "returnTx",
                }},
                {"$match": {"returnTx": {"$size": 0}}},
                {"$lookup": {
                    "from": "items",
                    "localField": "itemCode",
                    "foreignField": "itemCode",
                    "as": "itemInfo",
                }},
                {"$project": {
                    "_id": 0,
                    "itemCode": 1,
                    "itemName": {"$ifNull": [
                        {"$arrayElemAt": ["$itemInfo.itemName", 0]},
                        "Unknown Item",
                    ]},
                    "issuedTo": 1,
                    "quantity": 1,
                    "issuedDate": "$timestamp",
                    "expectedReturnDate": 1,
                    "expected_return_date": 1,
                    "dueDate": 1,
                    "due_date": 1,
                }},
            ],

            # Recent damage reports
            "damagedReports": [
                {"$match": {"transactionType": "damage"}},
                {"$sort": {"timestamp": -1}},
                {"$limit": 10},
                {"$lookup": {
                    "from": "items",
                    "localField": "itemCode",
                    "foreignField": "itemCode",
                    "as": "itemInfo",
                }},
                {"$project": {
                    "_id": 0,
                    "itemCode": 1,
                    "itemName": {"$ifNull": [
                        {"$arrayElemAt": ["$itemInfo.itemName", 0]},
                        "Unknown Item",
                    ]},
                    "quantity": 1,
                    "reportedDate": "$timestamp",
                    "remarks": 1,
                }},
            ],
        }}
    ]
    try:
        result = list(db.transactions.aggregate(pipeline))
        return result[0] if result else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Alert builder
# ---------------------------------------------------------------------------

def _build_alerts(alert_items, damaged_reports):
    alerts = []
    now_iso = datetime.utcnow().isoformat()

    for item in alert_items:
        status_clean = (item.get('status') or '').lower().replace('_', ' ')
        if 'out' in status_clean:
            alerts.append({
                "type": "danger",
                "category": "out_of_stock",
                "message": f"Item '{item['itemName']}' ({item['itemCode']}) is out of stock!",
                "itemCode": item.get('itemCode'),
                "timestamp": now_iso,
                "metadata": {
                    "route": "/inventory",
                    "queryParams": {"status": "out_of_stock", "search": item.get('itemCode')},
                    "actionText": "Purchase Order"
                }
            })
        else:
            alerts.append({
                "type": "warning",
                "category": "low_stock",
                "message": (
                    f"Item '{item['itemName']}' ({item['itemCode']}) is running low! "
                    f"Only {item.get('availableQuantity', 0)} remaining."
                ),
                "itemCode": item.get('itemCode'),
                "timestamp": now_iso,
                "metadata": {
                    "route": "/inventory",
                    "queryParams": {"status": "low_stock", "search": item.get('itemCode')},
                    "actionText": "Review Stock"
                }
            })

    for dmg in damaged_reports:
        ts = dmg.get('reportedDate')
        alerts.append({
            "type": "info",
            "category": "damage",
            "message": (
                f"Damaged stock: {dmg['quantity']} unit(s) of "
                f"'{dmg.get('itemCode')}' marked as damaged."
            ),
            "itemCode": dmg.get('itemCode'),
            "timestamp": ts.isoformat() if hasattr(ts, 'isoformat') else (ts or now_iso),
            "metadata": {
                "route": "/inventory",
                "queryParams": {"status": "damaged", "search": dmg.get('itemCode')},
                "actionText": "Inspect Damage"
            }
        })

    return alerts


# ---------------------------------------------------------------------------
# Returns and Overdue builder
# ---------------------------------------------------------------------------

def _build_returns_and_overdue(issued_not_returned, user_filter=None):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)

    overdue_items = []
    today_returns = []
    returns_due = []

    for item in issued_not_returned:
        if user_filter and item.get('issuedTo') != user_filter:
            continue

        issued_date = item.get('issuedDate')
        if hasattr(issued_date, 'isoformat'):
            days_since = (now - issued_date).days
            issued_date_str = issued_date.isoformat()
        else:
            days_since = 0
            issued_date_str = str(issued_date or '')

        # Standard return due list (for ActionCenter)
        returns_due.append({
            "itemCode": item.get('itemCode'),
            "itemName": item.get('itemName', 'Unknown'),
            "issuedTo": item.get('issuedTo', ''),
            "issuedDate": issued_date_str,
            "quantity": item.get('quantity', 0),
            "daysSinceIssue": days_since,
        })

        # Expected return/due dates parsing
        expected_date = item.get('expectedReturnDate') or item.get('expected_return_date') or item.get('dueDate') or item.get('due_date')
        if not expected_date:
            continue

        parsed_expected = None
        if isinstance(expected_date, str):
            try:
                parsed_expected = datetime.fromisoformat(expected_date.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                try:
                    parsed_expected = datetime.strptime(expected_date, "%Y-%m-%d")
                except Exception:
                    pass
        elif isinstance(expected_date, datetime):
            parsed_expected = expected_date.replace(tzinfo=None)

        if not parsed_expected:
            continue

        expected_str = parsed_expected.isoformat()
        overdue_entry = {
            "itemCode": item.get('itemCode'),
            "itemName": item.get('itemName', 'Unknown'),
            "issuedTo": item.get('issuedTo', ''),
            "issuedDate": issued_date_str,
            "expectedReturnDate": expected_str,
            "quantity": item.get('quantity', 0),
        }

        if parsed_expected < today_start:
            overdue_entry["daysOverdue"] = (now - parsed_expected).days
            overdue_items.append(overdue_entry)
        elif today_start <= parsed_expected < today_end:
            today_returns.append(overdue_entry)

    return overdue_items, today_returns, returns_due


# ---------------------------------------------------------------------------
# Dynamically fetch optional collections
# ---------------------------------------------------------------------------

def _get_asset_requests(user_id=None, role=None):
    try:
        from bson import ObjectId
        query = {}
        
        if role == "team_member" and user_id:
            query["requestedBy"] = ObjectId(user_id)
            query["status"] = {"$in": ["pending_manager", "pending_store_head"]}
        elif role == "manager":
            query["status"] = "pending_manager"
            # Limit manager's dashboard view of pending requests to their department if desired,
            # but for simplicity, global pending_manager requests are fine.
        elif role in ["store_head", "admin"]:
            query["status"] = "pending_store_head"
        else:
            # viewer or fallback
            return []

        requests_cursor = db.asset_requests.find(query).sort("createdAt", -1).limit(20)
        requests = []
        for req in requests_cursor:
            req_dict = dict(req)
            req_dict["id"] = str(req_dict["_id"])
            req_dict.pop("_id", None)
            
            # Scrub ObjectIds and convert datetime
            for k, v in req_dict.items():
                if isinstance(v, ObjectId):
                    req_dict[k] = str(v)
            
            # Serialize dates
            for key in ["requestDate", "createdAt", "updatedAt", "requiredFrom", "requiredUntil"]:
                val = req_dict.get(key)
                if hasattr(val, 'isoformat'):
                    req_dict[key] = val.isoformat()
            requests.append(req_dict)
        return requests
    except Exception:
        return []


def _get_notifications_alerts():
    try:
        notifications_cursor = db.notifications.find({}).sort("timestamp", -1).limit(10)
        alerts = []
        for n in notifications_cursor:
            alerts.append({
                "type": n.get("type", "info"),
                "category": n.get("category", "system"),
                "message": n.get("message", ""),
                "itemCode": n.get("itemCode"),
                "timestamp": n.get("timestamp").isoformat() if hasattr(n.get("timestamp"), 'isoformat') else str(n.get("timestamp", "")),
                "metadata": n.get("metadata", {})
            })
        return alerts
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Serialization helper for timestamps in recent transactions
# ---------------------------------------------------------------------------

def _serialize_transactions(txs):
    serialized = []
    for tx in txs:
        entry = dict(tx)
        ts = entry.get('timestamp')
        if hasattr(ts, 'isoformat'):
            entry['timestamp'] = ts.isoformat()
        elif ts is None:
            entry['timestamp'] = ''
        serialized.append(entry)
    return serialized


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_dashboard_summary(user):
    """Build the complete dashboard payload for the given user.

    *user* is the dict injected by the auth middleware:
        {'id', 'username', 'email', 'role', ...}
    """
    role = user.get('role', 'viewer')
    user_id = user.get('id')

    # Check cache (team_member is per-user, others are per-role)
    cached = _get_cached(role, user_id)
    if cached:
        cached['meta']['cachedUntil'] = (
            datetime.utcnow() + timedelta(seconds=_CACHE_TTL)
        ).isoformat()
        return cached

    # ---- Run aggregation pipelines ----
    items_data = _run_items_pipeline()
    invoices_data = _run_invoices_pipeline()

    # For team_member, filter transactions to their own
    user_email = user.get('email', '')
    user_name = user.get('username', '')
    tx_filter = user_email if role == 'team_member' else None
    transactions_data = _run_transactions_pipeline(user_filter=tx_filter)

    # ---- Extract facet results ----
    def _count(facet_result, key):
        arr = facet_result.get(key, [])
        return arr[0].get('count', 0) if arr else 0

    total_items = _count(items_data, 'totalItems')
    stock_totals = items_data.get('stockTotals', [{}])
    stock = stock_totals[0] if stock_totals else {}
    available_items = stock.get('totalAvailable', 0)
    issued_items = stock.get('totalIssued', 0)
    low_stock_items = _count(items_data, 'lowStockItems')
    out_of_stock_items = _count(items_data, 'outOfStockItems')
    damaged_items_count = _count(items_data, 'damagedItems')

    inv_totals = invoices_data.get('invoiceTotals', [{}])
    inv = inv_totals[0] if inv_totals else {}
    total_invoices = inv.get('totalInvoices', 0)
    total_purchase_value = round(inv.get('totalPurchaseValue', 0), 2)

    # Users (only for admin)
    total_users = None
    active_users = None
    if role == 'admin':
        try:
            total_users = db.users.count_documents({})
            active_users = db.users.count_documents({"isActive": True})
        except Exception:
            pass

    # ---- Build response sections ----
    category_wise = items_data.get('categoryWiseStock', [])
    status_wise = items_data.get('statusWiseStock', [])
    recent_txs = _serialize_transactions(
        transactions_data.get('recentTransactions', [])
    )

    # Alerts (Merge notifications and dynamic item alerts)
    alert_items = items_data.get('alertItems', [])
    damaged_reports = transactions_data.get('damagedReports', [])
    alerts = _build_alerts(alert_items, damaged_reports)
    notifications = _get_notifications_alerts()
    all_alerts = notifications + alerts

    # Action center / returns / overdue
    issued_not_returned = transactions_data.get('issuedNotReturned', [])
    overdue_items, today_returns, returns_due = _build_returns_and_overdue(
        issued_not_returned,
        user_filter=user_email if role == 'team_member' else None,
    )

    # Serialized damaged reports for action center
    damaged_review = []
    for dmg in damaged_reports:
        ts = dmg.get('reportedDate')
        damaged_review.append({
            "itemCode": dmg.get('itemCode'),
            "itemName": dmg.get('itemName', 'Unknown Item'),
            "quantity": dmg.get('quantity', 0),
            "reportedDate": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts or ''),
            "remarks": dmg.get('remarks', ''),
        })

    # Optional Asset Requests and approvals
    pending_requests = _get_asset_requests(user_id=user_id, role=role)
    if role in ['admin', 'store_head', 'manager']:
        from services.approval_engine_service import list_pending_reviews
        pending_approvals = list_pending_reviews(user)
    else:
        pending_approvals = []

    now_iso = datetime.utcnow().isoformat()

    # ---- Assemble full payload ----
    payload = {
        # 1. Flat top-level structure (User explicit requirements)
        "totalItems": total_items,
        "availableItems": available_items,
        "issuedItems": issued_items,
        "lowStockItems": low_stock_items,
        "totalPurchaseValue": total_purchase_value,
        "totalInvoices": total_invoices,
        "recentTransactions": recent_txs,
        "categoryWiseStock": category_wise,
        "statusWiseStock": status_wise,
        "overdueItems": overdue_items,
        "alerts": all_alerts,
        "pendingRequests": pending_requests,
        "pendingApprovals": pending_approvals,
        "todayReturns": today_returns,
        "damagedItems": damaged_review,

        # 2. Nested structure (for existing React frontend backward compatibility)
        "summary": {
            "totalItems": total_items,
            "availableItems": available_items,
            "issuedItems": issued_items,
            "lowStockItems": low_stock_items,
            "outOfStockItems": out_of_stock_items,
            "damagedItems": damaged_items_count,
            "totalPurchaseValue": total_purchase_value,
            "totalInvoices": total_invoices,
            "totalUsers": total_users,
            "activeUsers": active_users,
        },
        "actionCenter": {
            "pendingAssetRequests": pending_requests,
            "lowStockRequiringPurchase": items_data.get('lowStockRequiringPurchase', []),
            "todaysReturnsDue": returns_due,
            "pendingApprovals": pending_approvals,
            "damagedItemsNeedingReview": damaged_review,
        },
        "meta": {
            "generatedAt": now_iso,
            "cachedUntil": None,
            "userRole": role,
        },
    }

    # ---- Apply role-based filtering ----
    payload = _apply_role_filter(payload, role, returns_due)

    # ---- Cache ----
    _set_cached(role, payload, user_id)

    return payload


# ---------------------------------------------------------------------------
# Role-based response filtering
# ---------------------------------------------------------------------------

def _apply_role_filter(payload, role, returns_due):
    """Strip or shape fields the given role should not see."""
    if role == 'team_member':
        # team_member sees only their own relevant metrics
        payload['totalItems'] = len(returns_due)
        payload['availableItems'] = None
        payload['issuedItems'] = sum(item.get('quantity', 0) for item in returns_due)
        payload['lowStockItems'] = 0
        payload['totalPurchaseValue'] = None
        payload['totalInvoices'] = None
        payload['categoryWiseStock'] = []
        payload['statusWiseStock'] = []
        payload['alerts'] = []
        payload['pendingApprovals'] = []
        payload['damagedItems'] = []

        # Update nested summary to match
        payload['summary']['totalItems'] = len(returns_due)
        payload['summary']['availableItems'] = None
        payload['summary']['issuedItems'] = sum(item.get('quantity', 0) for item in returns_due)
        payload['summary']['lowStockItems'] = 0
        payload['summary']['outOfStockItems'] = 0
        payload['summary']['damagedItems'] = 0
        payload['summary']['totalPurchaseValue'] = None
        payload['summary']['totalInvoices'] = None
        payload['summary']['totalUsers'] = None
        payload['summary']['activeUsers'] = None
        
        # Update action center
        payload['actionCenter']['lowStockRequiringPurchase'] = []
        payload['actionCenter']['pendingApprovals'] = []
        payload['actionCenter']['damagedItemsNeedingReview'] = []

    elif role == 'viewer':
        # Viewer gets read-only stats + charts, no action center or financial data
        payload['totalPurchaseValue'] = None
        payload['totalInvoices'] = None
        payload['pendingRequests'] = []
        payload['pendingApprovals'] = []
        payload['todayReturns'] = []
        payload['damagedItems'] = []

        # Update nested summary to match
        payload['summary']['totalPurchaseValue'] = None
        payload['summary']['totalInvoices'] = None
        payload['summary']['totalUsers'] = None
        payload['summary']['activeUsers'] = None
        
        # Update action center
        payload['actionCenter'] = {
            "pendingAssetRequests": [],
            "lowStockRequiringPurchase": [],
            "todaysReturnsDue": [],
            "pendingApprovals": [],
            "damagedItemsNeedingReview": [],
        }

    elif role == 'store_head':
        # Store head sees everything except user management stats
        payload['summary']['totalUsers'] = None
        payload['summary']['activeUsers'] = None

    # admin sees everything — no filtering needed

    return payload


def get_recent_activity(user, limit=15):
    role = user.get('role', 'viewer')
    user_email = user.get('email', '')
    
    activities = []
    
    # 1. Fetch transactions
    tx_query = {}
    if role == 'team_member':
        tx_query['$or'] = [
            {'issuedTo': user_email},
            {'actionByEmail': user_email}
        ]
        
    txs = list(db.transactions.find(tx_query).sort('timestamp', -1).limit(limit))
    
    for tx in txs:
        # Determine human-readable message
        txtype = tx.get('transactionType', '')
        qty = tx.get('quantity', 0)
        code = tx.get('itemCode', '')
        issued_to = tx.get('issuedTo', '')
        by = tx.get('actionByEmail', 'System')
        if not isinstance(by, str):
            by = str(by)
        
        msg = f"Performed transaction of type '{txtype}' on '{code}'"
        if txtype == 'issue':
            msg = f"Issued {qty} of '{code}' to '{issued_to}'"
        elif txtype == 'return':
            msg = f"Returned {qty} of '{code}' to store"
        elif txtype == 'consume':
            msg = f"Consumed {qty} of '{code}'"
        elif txtype == 'damage':
            msg = f"Logged {qty} damaged units of '{code}'"
        elif txtype == 'transfer':
            from_loc = tx.get('fromLocation', '')
            to_loc = tx.get('toLocation', '')
            msg = f"Transferred '{code}' from '{from_loc}' to '{to_loc}'"
        elif txtype == 'adjust':
            msg = f"Adjusted stock for '{code}'"
        elif txtype == 'lost':
            msg = f"Logged {qty} lost units of '{code}'"
        elif txtype == 'repair':
            action = tx.get('repairAction', 'send')
            msg = f"Logged repair '{action}' for {qty} of '{code}'"
            
        activities.append({
            'id': str(tx['_id']),
            'type': 'transaction',
            'action': f"item_{txtype}" if txtype in ['issue', 'return', 'damage'] else 'stock_adjusted',
            'message': msg,
            'user': by,
            'timestamp': tx['timestamp'].isoformat() if tx.get('timestamp') and hasattr(tx.get('timestamp'), 'isoformat') else str(tx.get('timestamp') or ''),
            'entityType': 'item',
            'entityId': code
        })
        
    # 2. Fetch high-profile audit logs (only for admin and store_head)
    if role in ['admin', 'store_head']:
        audit_query = {
            'action': {
                '$in': [
                    'invoice_uploaded',
                    'user_created',
                    'user_disabled',
                    'user_enabled',
                    'item_created',
                    'item_updated'
                ]
            }
        }
        logs = list(db.audit_logs.find(audit_query).sort('timestamp', -1).limit(limit))
        for log in logs:
            activities.append({
                'id': str(log['_id']),
                'type': 'audit',
                'action': log.get('action', ''),
                'message': log.get('details', ''),
                'user': log.get('performedByUsername', 'System'),
                'timestamp': log['timestamp'].isoformat() if log.get('timestamp') and hasattr(log.get('timestamp'), 'isoformat') else str(log.get('timestamp') or ''),
                'entityType': log.get('entityType'),
                'entityId': log.get('entityId')
            })
            
    # Sort unified activities chronologically
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:limit]
