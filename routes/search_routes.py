from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required
from utils.db import db

search_bp = Blueprint("search", __name__)

@search_bp.route("/global", methods=["GET"])
@token_required
def global_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"items": [], "users": [], "invoices": []}), 200
        
    # Search items
    item_cursor = db.items.find({
        "$or": [
            {"itemName": {"$regex": q, "$options": "i"}},
            {"itemCode": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
            {"model": {"$regex": q, "$options": "i"}},
            {"location": {"$regex": q, "$options": "i"}}
        ]
    }).limit(10)
    
    items = []
    for item in item_cursor:
        items.append({
            "id": str(item["_id"]),
            "label": f"{item.get('itemName')} ({item.get('itemCode')})",
            "itemCode": item.get("itemCode"),
            "category": item.get("category"),
            "url": f"/inventory/{item.get('itemCode')}"
        })
        
    # Search users
    user_cursor = db.users.find({
        "$or": [
            {"username": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}}
        ]
    }).limit(5)
    
    users = []
    for u in user_cursor:
        users.append({
            "id": str(u["_id"]),
            "label": f"{u.get('name') or u.get('username')} ({u.get('email')})",
            "email": u.get("email"),
            "url": "/users"
        })
        
    # Search invoices
    invoice_cursor = db.invoices.find({
        "$or": [
            {"invoiceNumber": {"$regex": q, "$options": "i"}},
            {"vendor": {"$regex": q, "$options": "i"}}
        ]
    }).limit(5)
    
    invoices = []
    for inv in invoice_cursor:
        invoices.append({
            "id": str(inv["_id"]),
            "label": f"Invoice {inv.get('invoiceNumber')} - {inv.get('vendor')}",
            "invoiceNumber": inv.get("invoiceNumber"),
            "url": "/invoices"
        })
        
    return jsonify({
        "items": items,
        "users": users,
        "invoices": invoices
    }), 200
