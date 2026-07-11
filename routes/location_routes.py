from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.location_service import (
    create_location,
    list_locations,
    get_location_contents,
    seed_default_locations,
    create_warehouse,
    list_warehouses
)
from services.location_movement_service import (
    move_item,
    list_movements
)

location_bp = Blueprint("locations", __name__)

@location_bp.route("/seed", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def seed_locations():
    from config import Config
    if Config.ENV == 'production':
        return jsonify({"message": "Seeding database locations is prohibited in production mode."}), 403
    try:
        seed_default_locations()
        return jsonify({"message": "Locations seeded successfully"}), 200
    except Exception as e:
        return jsonify({"message": "Failed to seed locations", "error": str(e)}), 500

@location_bp.route("", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def add_location():
    try:
        data = request.get_json()
        loc_code = create_location(data)
        return jsonify({"message": "Location created successfully", "locationCode": loc_code}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to create location", "error": str(e)}), 500

@location_bp.route("", methods=["GET"])
@token_required
def get_locations():
    try:
        wh_code = request.args.get("warehouseCode")
        zone_code = request.args.get("zoneCode")
        locs = list_locations(warehouse_code=wh_code, zone_code=zone_code)
        return jsonify({"locations": locs}), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve locations", "error": str(e)}), 500

@location_bp.route("/contents", methods=["GET"])
@token_required
def get_contents():
    try:
        loc_code = request.args.get("locationCode")
        if not loc_code:
            return jsonify({"message": "locationCode query parameter is required"}), 400
        contents = get_location_contents(loc_code)
        return jsonify({"contents": contents}), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve location contents", "error": str(e)}), 500

@location_bp.route("/move", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def transfer_item():
    try:
        data = request.get_json()
        item_id = data.get("itemId")
        serial_number = data.get("serialNumber")
        dest_loc = data.get("destinationLocationCode")
        qty = data.get("quantity", 1)
        reason = data.get("reason", "Internal Transfer")
        
        if not item_id or not dest_loc:
            return jsonify({"message": "itemId and destinationLocationCode are required"}), 400
            
        operator = request.user
        mov_id = move_item(item_id, serial_number, dest_loc, qty, operator, reason)
        return jsonify({"message": "Asset transferred successfully", "movementId": mov_id}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to perform transfer", "error": str(e)}), 500

@location_bp.route("/movements", methods=["GET"])
@token_required
def get_movements():
    try:
        item_code = request.args.get("itemCode")
        limit = int(request.args.get("limit", 50))
        movements = list_movements(item_code=item_code, limit=limit)
        return jsonify({"movements": movements}), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve movements history", "error": str(e)}), 500

@location_bp.route("/warehouses", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def add_warehouse():
    try:
        data = request.get_json()
        wh_id = create_warehouse(data)
        return jsonify({"message": "Warehouse created successfully", "warehouseId": wh_id}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to create warehouse", "error": str(e)}), 500

@location_bp.route("/warehouses", methods=["GET"])
@token_required
def get_warehouses():
    try:
        whs = list_warehouses()
        return jsonify({"warehouses": whs}), 200
    except Exception as e:
        return jsonify({"message": "Failed to retrieve warehouses", "error": str(e)}), 500
