import datetime
from utils.db import db

def seed_default_locations():
    """Seeds sample warehouses and locations for layout visualizer and lookup."""
    try:
        # Seed warehouses
        if db.warehouses.count_documents({}) == 0:
            db.warehouses.insert_many([
                {
                    "warehouseId": "WH1",
                    "name": "Main Warehouse Bengaluru",
                    "address": "Electronic City Phase 1, Bengaluru",
                    "status": "active",
                    "createdAt": datetime.datetime.utcnow(),
                    "updatedAt": datetime.datetime.utcnow()
                },
                {
                    "warehouseId": "WH2",
                    "name": "Secondary Hub Chennai",
                    "address": "OMR Road, Chennai",
                    "status": "active",
                    "createdAt": datetime.datetime.utcnow(),
                    "updatedAt": datetime.datetime.utcnow()
                }
            ])

        # Check if already seeded
        if db.locations.count_documents({}) > 0:
            return
            
        warehouses = [
            {"code": "WH1", "name": "Main Warehouse Bengaluru"},
            {"code": "WH2", "name": "Secondary Hub Chennai"}
        ]
        
        zones = [
            {"code": "ZA", "name": "Zone A - Hardware & Server Racks"},
            {"code": "ZB", "name": "Zone B - General Stationery & Cables"},
            {"code": "ZC", "name": "Zone C - Mobile Devices & Accessories"}
        ]
        
        locations_to_insert = []
        
        for wh in warehouses:
            for zone in zones:
                # Create 3 racks, 3 shelves, 2 bins per shelf
                for r_num in range(1, 4):
                    rack_code = f"R{r_num:02d}"
                    for s_num in range(1, 4):
                        shelf_code = f"S{s_num:02d}"
                        for b_num in range(1, 3):
                            bin_code = f"B{b_num:02d}"
                            
                            loc_code = f"{wh['code']}-{zone['code']}-{rack_code}-{shelf_code}-{bin_code}"
                            
                            # Give varying capacities based on zones
                            max_weight = 100 if zone["code"] == "ZA" else 50
                            max_vol = 80000 if zone["code"] == "ZA" else 40000
                            
                            locations_to_insert.append({
                                "locationCode": loc_code,
                                "warehouse": wh,
                                "zone": zone,
                                "rack": {"code": rack_code, "name": f"Rack {r_num}"},
                                "shelf": {"code": shelf_code, "name": f"Shelf {s_num}"},
                                "bin": {"code": bin_code, "name": f"Bin {b_num}"},
                                "dimensions": {
                                    "width": 60,
                                    "height": 40,
                                    "depth": 50,
                                    "unit": "cm"
                                },
                                "capacity": {
                                    "maxWeight": max_weight,
                                    "weightUnit": "kg",
                                    "maxVolume": max_vol,
                                    "volumeUnit": "cm3"
                                },
                                "status": "active",
                                "createdAt": datetime.datetime.utcnow(),
                                "updatedAt": datetime.datetime.utcnow()
                            })
                            
        db.locations.insert_many(locations_to_insert)
        print(f"Seeded {len(locations_to_insert)} warehouse locations successfully.")
    except Exception as e:
        print(f"Failed to seed locations: {e}")

def create_location(data):
    """Creates a new storage location coordinate."""
    loc_code = data.get("locationCode")
    if not loc_code:
        raise ValueError("locationCode is required")
        
    # Check if duplicate
    existing = db.locations.find_one({"locationCode": loc_code})
    if existing:
        raise ValueError(f"Location {loc_code} already exists")
        
    # Extract components
    parts = loc_code.split("-")
    if len(parts) < 5:
        raise ValueError("locationCode must follow format: WH-ZONE-RACK-SHELF-BIN")
        
    wh_code, zone_code, rack_code, shelf_code, bin_code = parts[0], parts[1], parts[2], parts[3], parts[4]
    
    doc = {
        "locationCode": loc_code,
        "warehouse": {"code": wh_code, "name": data.get("warehouseName", f"Warehouse {wh_code}")},
        "zone": {"code": zone_code, "name": data.get("zoneName", f"Zone {zone_code}")},
        "rack": {"code": rack_code, "name": f"Rack {rack_code}"},
        "shelf": {"code": shelf_code, "name": f"Shelf {shelf_code}"},
        "bin": {"code": bin_code, "name": f"Bin {bin_code}"},
        "dimensions": data.get("dimensions", {"width": 50, "height": 30, "depth": 40, "unit": "cm"}),
        "capacity": data.get("capacity", {"maxWeight": 100, "weightUnit": "kg", "maxVolume": 60000, "volumeUnit": "cm3"}),
        "status": data.get("status", "active"),
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.locations.insert_one(doc)
    return loc_code

def list_locations(warehouse_code=None, zone_code=None):
    """Lists configured locations and calculates dynamic occupancy counts."""
    query = {"status": "active"}
    if warehouse_code:
        query["warehouse.code"] = warehouse_code
    if zone_code:
        query["zone.code"] = zone_code
        
    locs = list(db.locations.find(query).sort("locationCode", 1))
    
    # Calculate occupancy stats
    for loc in locs:
        loc["_id"] = str(loc["_id"])
        if isinstance(loc.get("createdAt"), datetime.datetime):
            loc["createdAt"] = loc["createdAt"].isoformat()
        if isinstance(loc.get("updatedAt"), datetime.datetime):
            loc["updatedAt"] = loc["updatedAt"].isoformat()
            
        loc_code = loc["locationCode"]
        
        # Serialized count
        ser_count = db.items.count_documents({"locationCode": loc_code})
        
        # Bulk allocations count
        bulk_pipeline = [
            {"$match": {"stockAllocations.locationCode": loc_code}},
            {"$unwind": "$stockAllocations"},
            {"$match": {"stockAllocations.locationCode": loc_code}},
            {"$group": {"_id": None, "total": {"$sum": "$stockAllocations.quantity"}}}
        ]
        bulk_res = list(db.items.aggregate(bulk_pipeline))
        bulk_qty = bulk_res[0]["total"] if bulk_res else 0
        
        total_qty = ser_count + bulk_qty
        loc["itemCount"] = total_qty
        
        # Mocking occupancy rate percentage based on itemCount capacity threshold
        # If capacity doesn't have maxItems, assume threshold of 20 items per bin
        max_items = loc.get("capacity", {}).get("maxItems", 20)
        loc["occupancyRate"] = min(100, round((total_qty / max_items) * 100))
        
    return locs

def get_location_contents(location_code):
    """Retrieves all active items and physical units stored inside a location."""
    # Find serialized items
    items_cursor = db.items.find({"locationCode": location_code})
    serialized_list = []
    for item in items_cursor:
        serialized_list.append({
            "itemId": str(item["_id"]),
            "itemCode": item["itemCode"],
            "itemName": item["itemName"],
            "category": item["category"],
            "serialNumber": item.get("serialNumber"),
            "quantity": 1,
            "isSerialized": True
        })
        
    # Find bulk items with allocations
    bulk_cursor = db.items.find({"stockAllocations.locationCode": location_code})
    bulk_list = []
    for item in bulk_cursor:
        # Extract specific allocation
        qty = 0
        for alloc in item.get("stockAllocations", []):
            if alloc.get("locationCode") == location_code:
                qty += alloc.get("quantity", 0)
        if qty > 0:
            bulk_list.append({
                "itemId": str(item["_id"]),
                "itemCode": item["itemCode"],
                "itemName": item["itemName"],
                "category": item["category"],
                "quantity": qty,
                "isSerialized": False
            })
            
    return serialized_list + bulk_list

def create_warehouse(data):
    """Creates a new warehouse node."""
    wh_id = data.get("warehouseId")
    if not wh_id:
        raise ValueError("warehouseId is required")
        
    existing = db.warehouses.find_one({"warehouseId": wh_id})
    if existing:
        raise ValueError(f"Warehouse {wh_id} already exists")
        
    doc = {
        "warehouseId": wh_id,
        "name": data.get("name", f"Warehouse {wh_id}"),
        "address": data.get("address", ""),
        "status": data.get("status", "active"),
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow()
    }
    
    db.warehouses.insert_one(doc)
    return wh_id

def list_warehouses():
    """Lists all warehouses in system."""
    whs = list(db.warehouses.find({}).sort("warehouseId", 1))
    for wh in whs:
        wh["_id"] = str(wh["_id"])
        if isinstance(wh.get("createdAt"), datetime.datetime):
            wh["createdAt"] = wh["createdAt"].isoformat()
        if isinstance(wh.get("updatedAt"), datetime.datetime):
            wh["updatedAt"] = wh["updatedAt"].isoformat()
    return whs
