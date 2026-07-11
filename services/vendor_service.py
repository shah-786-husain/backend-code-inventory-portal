import datetime
from bson import ObjectId
from utils.db import db
from services.audit_service import log_audit, get_dict_diff

def serialize_vendor(d):
    if not d:
        return None
    return {
        "id": str(d["_id"]),
        "vendorCode": d.get("vendorCode"),
        "vendorName": d.get("vendorName"),
        "contactPerson": d.get("contactPerson"),
        "email": d.get("email"),
        "phone": d.get("phone"),
        "address": d.get("address"),
        "gstNumber": d.get("gstNumber"),
        "notes": d.get("notes"),
        "isActive": d.get("isActive", True),
        "createdAt": d.get("createdAt").isoformat() if d.get("createdAt") else "",
        "updatedAt": d.get("updatedAt").isoformat() if d.get("updatedAt") else ""
    }

def create_vendor(data, user_email):
    vendor_name = data.get("vendorName", "").strip()
    if not vendor_name:
        raise ValueError("vendorName is required")
        
    # Check for duplicate vendorName
    existing = db.vendors.find_one({"vendorName": {"$regex": f"^{vendor_name}$", "$options": "i"}})
    if existing:
        raise ValueError(f"Vendor '{vendor_name}' already exists")
        
    # Calculate sequential vendorCode
    count = db.vendors.count_documents({})
    vendor_code = f"VEN-{str(count + 1).zfill(4)}"
    
    doc = {
        "vendorCode": vendor_code,
        "vendorName": vendor_name,
        "contactPerson": data.get("contactPerson", "").strip(),
        "email": data.get("email", "").strip(),
        "phone": data.get("phone", "").strip(),
        "address": data.get("address", "").strip(),
        "gstNumber": data.get("gstNumber", "").strip(),
        "notes": data.get("notes", "").strip(),
        "isActive": data.get("isActive", True),
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }
    
    res = db.vendors.insert_one(doc)
    doc["_id"] = res.inserted_id
    
    log_audit(
        action="vendor_created",
        details=f"Vendor {vendor_name} ({vendor_code}) created by {user_email}",
        performed_by_id=None,
        performed_by_email=user_email,
        entity_type="vendor",
        entity_id=str(res.inserted_id),
        new_value=serialize_vendor(doc)
    )
    
    return serialize_vendor(doc)

def list_vendors(args):
    page = int(args.get("page", 1))
    limit = int(args.get("limit", 20))
    skip = (page - 1) * limit
    
    query = {}
    
    active_filter = args.get("isActive")
    if active_filter is not None:
        query["isActive"] = active_filter.lower() == "true"
        
    search = args.get("search", "").strip()
    if search:
        query["$or"] = [
            {"vendorCode": {"$regex": search, "$options": "i"}},
            {"vendorName": {"$regex": search, "$options": "i"}},
            {"contactPerson": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"gstNumber": {"$regex": search, "$options": "i"}}
        ]
        
    total = db.vendors.count_documents(query)
    docs = list(db.vendors.find(query).sort("createdAt", -1).skip(skip).limit(limit))
    
    formatted = [serialize_vendor(d) for d in docs]
    
    return {
        "items": formatted,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }

def get_vendor_detail(vendor_id_str):
    doc = db.vendors.find_one({"_id": ObjectId(vendor_id_str)})
    return serialize_vendor(doc)

def update_vendor(vendor_id_str, data, user_email):
    vendor_id_obj = ObjectId(vendor_id_str)
    existing = db.vendors.find_one({"_id": vendor_id_obj})
    if not existing:
        raise ValueError("Vendor not found")
        
    vendor_name = data.get("vendorName", "").strip()
    if vendor_name and vendor_name.lower() != existing["vendorName"].lower():
        dup = db.vendors.find_one({"vendorName": {"$regex": f"^{vendor_name}$", "$options": "i"}})
        if dup:
            raise ValueError(f"Vendor '{vendor_name}' already exists")
            
    updated_fields = {
        "updatedAt": datetime.datetime.utcnow()
    }
    for field in ["vendorName", "contactPerson", "email", "phone", "address", "gstNumber", "notes"]:
        if field in data:
            updated_fields[field] = data[field].strip() if isinstance(data[field], str) else data[field]
            
    db.vendors.update_one({"_id": vendor_id_obj}, {"$set": updated_fields})
    updated_doc = db.vendors.find_one({"_id": vendor_id_obj})
    
    old_val, new_val = get_dict_diff(existing, updated_doc)
    log_audit(
        action="vendor_updated",
        details=f"Vendor {existing['vendorName']} updated by {user_email}",
        performed_by_id=None,
        performed_by_email=user_email,
        entity_type="vendor",
        entity_id=vendor_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_vendor(updated_doc)

def toggle_vendor_status(vendor_id_str, user_email):
    vendor_id_obj = ObjectId(vendor_id_str)
    existing = db.vendors.find_one({"_id": vendor_id_obj})
    if not existing:
        raise ValueError("Vendor not found")
        
    new_status = not existing.get("isActive", True)
    
    db.vendors.update_one(
        {"_id": vendor_id_obj},
        {
            "$set": {
                "isActive": new_status,
                "updatedAt": datetime.datetime.utcnow()
            }
        }
    )
    updated_doc = db.vendors.find_one({"_id": vendor_id_obj})
    
    old_val, new_val = get_dict_diff(existing, updated_doc)
    log_audit(
        action="vendor_status_toggled",
        details=f"Vendor {existing['vendorName']} active status toggled to {new_status} by {user_email}",
        performed_by_id=None,
        performed_by_email=user_email,
        entity_type="vendor",
        entity_id=vendor_id_str,
        old_value=old_val,
        new_value=new_val
    )
    
    return serialize_vendor(updated_doc)

def get_vendor_dashboard_metrics():
    total_vendors = db.vendors.count_documents({})
    active_vendors = db.vendors.count_documents({"isActive": True})
    inactive_vendors = total_vendors - active_vendors
    
    # Aggregate total spend from all invoices
    pipeline_total_spend = [
        {"$group": {"_id": None, "total": {"$sum": "$totalAmount"}}}
    ]
    total_spend_res = list(db.invoices.aggregate(pipeline_total_spend))
    total_spend = total_spend_res[0]["total"] if total_spend_res else 0.0
    
    # Top vendors by spend
    vendors_list = list(db.vendors.find({}))
    top_vendors_by_spend = []
    
    for v in vendors_list:
        v_name = v["vendorName"]
        invoices = list(db.invoices.find({"vendor": {"$regex": f"^{v_name}$", "$options": "i"}}))
        spend = sum(inv.get("totalAmount", 0.0) for inv in invoices)
        invoice_count = len(invoices)
        item_count = db.items.count_documents({"vendor": {"$regex": f"^{v_name}$", "$options": "i"}})
        
        top_vendors_by_spend.append({
            "vendorId": str(v["_id"]),
            "vendorName": v_name,
            "totalSpend": spend,
            "invoiceCount": invoice_count,
            "itemCount": item_count
        })
        
    top_vendors_by_spend.sort(key=lambda x: x["totalSpend"], reverse=True)
    top_vendors_by_spend = top_vendors_by_spend[:5]
    
    # Recent vendor invoices
    recent_invoices_docs = list(db.invoices.find().sort("createdAt", -1).limit(5))
    recent_vendor_invoices = []
    for inv in recent_invoices_docs:
        recent_vendor_invoices.append({
            "invoiceId": str(inv["_id"]),
            "invoiceNumber": inv.get("invoiceNumber", ""),
            "vendorName": inv.get("vendor", ""),
            "amount": inv.get("totalAmount", 0.0),
            "purchaseDate": inv.get("purchaseDate", "")
        })
        
    vendor_spend_trend = []
    vendor_invoice_summary = []
    
    return {
        "totalVendors": total_vendors,
        "activeVendors": active_vendors,
        "inactiveVendors": inactive_vendors,
        "totalVendorSpend": total_spend,
        "topVendorsBySpend": top_vendors_by_spend,
        "recentVendorInvoices": recent_vendor_invoices,
        "vendorSpendTrend": vendor_spend_trend,
        "vendorInvoiceSummary": vendor_invoice_summary
    }

def get_vendor_specific_metrics(vendor_id_str):
    v = db.vendors.find_one({"_id": ObjectId(vendor_id_str)})
    if not v:
        raise ValueError("Vendor not found")
        
    v_name = v["vendorName"]
    invoices = list(db.invoices.find({"vendor": {"$regex": f"^{v_name}$", "$options": "i"}}))
    total_spend = sum(inv.get("totalAmount", 0.0) for inv in invoices)
    invoice_count = len(invoices)
    item_count = db.items.count_documents({"vendor": {"$regex": f"^{v_name}$", "$options": "i"}})
    
    recent_invoices = []
    for inv in sorted(invoices, key=lambda x: x.get("createdAt", datetime.datetime.min), reverse=True)[:5]:
        recent_invoices.append({
            "invoiceId": str(inv["_id"]),
            "invoiceNumber": inv.get("invoiceNumber", ""),
            "amount": inv.get("totalAmount", 0.0),
            "purchaseDate": inv.get("purchaseDate", "")
        })
        
    return {
        "totalInvoices": invoice_count,
        "totalSpend": total_spend,
        "itemsSupplied": item_count,
        "recentInvoices": recent_invoices
    }
