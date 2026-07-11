import datetime
from bson import ObjectId
from utils.db import db
from services.audit_service import log_audit

def move_item(item_id_str, serial_number, destination_location_code, quantity, operator, reason="Internal Transfer"):
    """Performs an asset location transfer, updating coordinates, allocations, and writing movement history."""
    item_id = ObjectId(item_id_str)
    item = db.items.find_one({"_id": item_id})
    if not item:
        raise ValueError("Item not found")
        
    # Check destination location exists
    dest_loc = db.locations.find_one({"locationCode": destination_location_code})
    if not dest_loc:
        raise ValueError(f"Destination location {destination_location_code} does not exist")
        
    parts = destination_location_code.split("-")
    if len(parts) < 5:
        raise ValueError("Destination location code must follow format: WH-ZONE-RACK-SHELF-BIN")
        
    loc_area = f"{parts[0]} - {parts[1]}"
    storage_unit = parts[2]
    compartment_row = parts[3]
    box_container = parts[4]
    
    source_location = ""
    is_serialized = item.get("isSerialized", True)
    
    if is_serialized:
        source_location = item.get("locationCode") or f"{item.get('locationArea', 'Unknown')}-{item.get('storageUnit', 'Unknown')}-{item.get('compartmentRow', 'Unknown')}-{item.get('boxContainer', 'Unknown')}"
        
        # Update serialized location and legacy fields
        db.items.update_one(
            {"_id": item_id},
            {
                "$set": {
                    "locationCode": destination_location_code,
                    "locationArea": loc_area,
                    "storageUnit": storage_unit,
                    "compartmentRow": compartment_row,
                    "boxContainer": box_container,
                    "updatedAt": datetime.datetime.utcnow()
                }
            }
        )
    else:
        # Bulk item movement
        # Source location should be passed or we assume first allocation with quantity >= move quantity
        allocations = list(item.get("stockAllocations", []))
        
        # Find matching source allocation
        source_alloc = None
        for alloc in allocations:
            if alloc.get("quantity", 0) >= quantity:
                source_alloc = alloc
                break
                
        if not source_alloc and len(allocations) > 0:
            source_alloc = allocations[0]
            
        if not source_alloc:
            raise ValueError("No stock allocation source found with sufficient quantity")
            
        source_location = source_alloc.get("locationCode")
        
        # Deduct from source
        source_alloc["quantity"] = max(0, source_alloc["quantity"] - quantity)
        
        # Add to destination
        dest_alloc = None
        for alloc in allocations:
            if alloc.get("locationCode") == destination_location_code:
                dest_alloc = alloc
                break
                
        if dest_alloc:
            dest_alloc["quantity"] += quantity
        else:
            allocations.append({
                "locationCode": destination_location_code,
                "quantity": quantity
            })
            
        # Clean out zero-quantity allocations
        allocations = [a for a in allocations if a.get("quantity", 0) > 0]
        
        # Update bulk allocations array in MongoDB
        db.items.update_one(
            {"_id": item_id},
            {
                "$set": {
                    "stockAllocations": allocations,
                    "updatedAt": datetime.datetime.utcnow()
                }
            }
        )
        
    # Generate movement ID
    mov_count = db.location_movements.count_documents({})
    mov_id = f"MOV-{datetime.datetime.utcnow().strftime('%Y%m')}-{mov_count + 1:04d}"
    
    movement_doc = {
        "movementId": mov_id,
        "itemId": item_id,
        "itemCode": item["itemCode"],
        "serialNumber": serial_number or item.get("serialNumber"),
        "quantity": quantity,
        "sourceLocationCode": source_location,
        "destinationLocationCode": destination_location_code,
        "reason": reason,
        "performedBy": operator.get("email"),
        "timestamp": datetime.datetime.utcnow(),
        "remarks": f"Moved via warehouse management tool. Operator: {operator.get('email')}"
    }
    
    db.location_movements.insert_one(movement_doc)
    
    # Log Audit Trail
    log_audit(
        "location_movement",
        f"Transferred item {item['itemCode']} ({quantity} units) from {source_location} to {destination_location_code}",
        operator.get("id"),
        operator.get("email"),
        "item",
        str(item_id),
        {"location": source_location},
        {"location": destination_location_code}
    )
    
    return mov_id

def list_movements(item_code=None, limit=50):
    """Retrieves list of all warehouse transfer records."""
    query = {}
    if item_code:
        query["itemCode"] = item_code
        
    movements = list(db.location_movements.find(query).sort("timestamp", -1).limit(limit))
    for mov in movements:
        mov["_id"] = str(mov["_id"])
        mov["itemId"] = str(mov["itemId"])
        if isinstance(mov.get("timestamp"), datetime.datetime):
            mov["timestamp"] = mov["timestamp"].isoformat()
            
    return movements
