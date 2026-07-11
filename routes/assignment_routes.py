from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.assignment_service import (
    issue_item_service,
    return_item_service,
    consume_item_service,
    damage_item_service,
    transfer_item_service,
    adjust_item_service,
    lost_item_service,
    repair_item_service,
    list_transactions_service,
    get_my_items_service,
    get_item_history_service,
    get_transaction_by_id_service
)

assignment_bp = Blueprint("assignment", __name__)

@assignment_bp.route("/issue", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def issue_item():
    try:
        data = request.get_json() or {}
        tx = issue_item_service(data, request.user)
        return jsonify({"message": "Item issued successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to issue item", "error": str(e)}), 500

@assignment_bp.route("/return", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def return_item():
    try:
        data = request.get_json() or {}
        tx = return_item_service(data, request.user)
        return jsonify({"message": "Item returned successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to return item", "error": str(e)}), 500

@assignment_bp.route("/consume", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def consume_item():
    try:
        data = request.get_json() or {}
        tx = consume_item_service(data, request.user)
        return jsonify({"message": "Consumable stock updated successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to consume item", "error": str(e)}), 500

@assignment_bp.route("/damage", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def damage_item():
    try:
        data = request.get_json() or {}
        tx = damage_item_service(data, request.user)
        return jsonify({"message": "Item damage logged and stock adjusted", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to log damage", "error": str(e)}), 500

@assignment_bp.route("/transfer", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def transfer_item():
    try:
        data = request.get_json() or {}
        tx = transfer_item_service(data, request.user)
        return jsonify({"message": "Item transfer logged successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to log transfer", "error": str(e)}), 500

@assignment_bp.route("/adjust", methods=["POST"])
@token_required
@role_required(["admin"])
def adjust_item():
    try:
        data = request.get_json() or {}
        tx = adjust_item_service(data, request.user)
        return jsonify({"message": "Stock reconciled successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to adjust stock", "error": str(e)}), 500

@assignment_bp.route("/lost", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def lost_item():
    try:
        data = request.get_json() or {}
        tx = lost_item_service(data, request.user)
        return jsonify({"message": "Lost item recorded successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to log lost item", "error": str(e)}), 500

@assignment_bp.route("/repair", methods=["POST"])
@token_required
@role_required(["admin", "store_head"])
def repair_item():
    try:
        data = request.get_json() or {}
        tx = repair_item_service(data, request.user)
        return jsonify({"message": "Repair maintenance action logged successfully", "transaction": str(tx.get('_id', ''))}), 200
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        return jsonify({"message": "Failed to log repair action", "error": str(e)}), 500

@assignment_bp.route("", methods=["GET"])
@token_required
def list_transactions():
    try:
        res = list_transactions_service(request.args, request.user)
        if 'page' in request.args:
            return jsonify({
                'items': res['transactions'],
                'pagination': res['pagination']
            }), 200
        else:
            return jsonify(res['transactions']), 200
    except Exception as e:
        return jsonify({"message": "Failed to list transactions", "error": str(e)}), 500

@assignment_bp.route("/my-items", methods=["GET"])
@token_required
def get_my_items():
    try:
        my_items = get_my_items_service(request.user)
        return jsonify(my_items), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch active items", "error": str(e)}), 500

@assignment_bp.route("/history/<item_code>", methods=["GET"])
@token_required
def get_item_history(item_code):
    try:
        history = get_item_history_service(item_code)
        return jsonify(history), 200
    except Exception as e:
        return jsonify({"message": "Failed to fetch item history", "error": str(e)}), 500


@assignment_bp.route("/<tx_id>", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "manager"])
def get_transaction_by_id(tx_id):
    try:
        tx = get_transaction_by_id_service(tx_id)
        if not tx:
            return jsonify({
                "success": False,
                "message": "Transaction not found",
                "errorCode": "NOT_FOUND",
                "details": None
            }), 404
        return jsonify(tx), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Failed to fetch transaction",
            "errorCode": "INTERNAL_ERROR",
            "details": str(e)
        }), 500
