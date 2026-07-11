from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required
from services.maintenance_service import (
    schedule_maintenance,
    update_maintenance_status,
    list_tickets,
    decommission_asset
)

maintenance_bp = Blueprint("maintenance", __name__)

@maintenance_bp.route("", methods=["GET"])
@token_required
def get_maintenance_tickets():
    try:
        filters = {
            "itemCode": request.args.get("itemCode"),
            "status": request.args.get("status"),
            "maintenanceType": request.args.get("maintenanceType")
        }
        tickets = list_tickets(filters)
        return jsonify({"success": True, "movements": tickets, "locations": tickets, "tickets": tickets, "maintenance": tickets}), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch maintenance tickets", "error": str(e)}), 500

@maintenance_bp.route("", methods=["POST"])
@token_required
def create_maintenance_ticket():
    try:
        user = request.user
        # Allow admin, store_head, manager to schedule maintenance
        if user["role"] not in ["admin", "store_head", "manager"]:
            return jsonify({"message": "Forbidden: insufficient permissions"}), 403

        data = request.get_json() or {}
        ticket = schedule_maintenance(data, user)
        return jsonify({"message": "Maintenance scheduled successfully", "ticket": ticket}), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to schedule maintenance", "error": str(e)}), 500

@maintenance_bp.route("/<string:mnt_id>", methods=["PATCH"])
@token_required
def update_ticket(mnt_id):
    try:
        user = request.user
        if user["role"] not in ["admin", "store_head", "manager"]:
            return jsonify({"message": "Forbidden: insufficient permissions"}), 403

        data = request.get_json() or {}
        updated_ticket = update_maintenance_status(mnt_id, data, user)
        return jsonify({"message": "Maintenance ticket updated successfully", "ticket": updated_ticket}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to update maintenance ticket", "error": str(e)}), 500

@maintenance_bp.route("/decommission/<string:item_code>", methods=["POST"])
@token_required
def decommission(item_code):
    try:
        user = request.user
        # Only admin and store_head can decommission asset
        if user["role"] not in ["admin", "store_head"]:
            return jsonify({"message": "Forbidden: insufficient permissions"}), 403

        data = request.get_json() or {}
        item = decommission_asset(item_code, data, user)
        return jsonify({"message": "Asset decommissioned successfully", "item": item}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to decommission asset", "error": str(e)}), 500
