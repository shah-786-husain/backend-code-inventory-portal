from flask import Blueprint, request, jsonify, Response
from utils.jwt_helper import token_required, role_required
from services.audit_service import log_audit, get_dict_diff
from services.item_service import (
    create_item_from_form,
    list_items,
    get_item,
    serialize_item,
    get_inventory_options,
    update_item_from_form,
    suggest_item_code,
    get_item_by_code,
    generate_qr_svg,
)

item_bp = Blueprint('item_bp', __name__)

@item_bp.route('', methods=['GET'])
@token_required
def get_items():
    res = list_items(request.args)
    return jsonify({
        'items': res['items'],
        'total': res['total'],
        'page': res['page'],
        'limit': res['limit'],
        'totalPages': res['totalPages'],
        'pagination': res['pagination']
    }), 200

@item_bp.route('/options', methods=['GET'])
@token_required
def get_item_options():
    return jsonify(get_inventory_options()), 200

@item_bp.route('/suggest-code', methods=['POST'])
@token_required
@role_required(['admin', 'store_head'])
def suggest_item_code_route():
    try:
        data = request.get_json(silent=True) or {}
        category = data.get('category', '')
        item_type = data.get('itemType', '')
        item_name = data.get('itemName', '')
        subcategory = data.get('subcategory', '')

        suggested_code = suggest_item_code(category, item_type, item_name, subcategory)

        return jsonify({
            'success': True,
            'suggestedCode': suggested_code,
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
        }), 500

@item_bp.route('', methods=['POST'])
@token_required
@role_required(['admin', 'store_head'])
def create_item():
    try:
        data = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        item = create_item_from_form(data, request.files)
        # Log audit trail
        log_audit(
            action='item_created', 
            details=f"Item '{item.get('itemName')}' ({item.get('itemCode')}) created with initial quantity {item.get('quantity')}", 
            performed_by_id=request.user['id'], 
            performed_by_email=request.user['email'],
            entity_type='item',
            entity_id=str(item.get('_id', '')),
            new_value=item,
            ip_address=request.remote_addr
        )
        return jsonify({
            'message': 'Item added successfully',
            'item': serialize_item(item),
            'itemCode': item.get('itemCode', ''),
        }), 201
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Failed to add item: {str(e)}'}), 500

@item_bp.route('/code/<item_code>', methods=['GET'])
@token_required
def get_item_by_code_route(item_code):
    item = get_item_by_code(item_code)
    if not item:
        return jsonify({'message': 'Item not found'}), 404
    return jsonify({'item': item}), 200

@item_bp.route('/<item_id>', methods=['GET'])
@token_required
def get_single_item(item_id):
    item = get_item(item_id)
    if not item:
        return jsonify({'message': 'Item not found'}), 404
    return jsonify(item), 200

@item_bp.route('/<item_id>', methods=['PUT', 'PATCH'])
@token_required
@role_required(['admin', 'store_head'])
def update_single_item(item_id):
    try:
        old_item = get_item(item_id)
        data = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        item = update_item_from_form(item_id, data, request.files)
        if not item:
            return jsonify({'message': 'Item not found'}), 404
            
        old_val, new_val = get_dict_diff(old_item, item)
            
        log_audit(
            action='item_updated', 
            details=f"Item details for '{item.get('itemCode')}' updated", 
            performed_by_id=request.user['id'], 
            performed_by_email=request.user['email'],
            entity_type='item',
            entity_id=item_id,
            old_value=old_val,
            new_value=new_val,
            ip_address=request.remote_addr
        )
        return jsonify({'message': 'Item updated successfully', 'item': item}), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Failed to update item: {str(e)}'}), 500


@item_bp.route('/qr', methods=['GET'])
def get_qr_code():
    try:
        code = request.args.get('code', '').strip()
        if not code:
            return jsonify({'message': 'Missing code parameter'}), 400
            
        svg_data = generate_qr_svg(code)
        return Response(svg_data, mimetype='image/svg+xml')
    except Exception as e:
        return jsonify({'message': f'Failed to generate QR: {str(e)}'}), 500


@item_bp.route('/code/<item_code>/label-data', methods=['GET'])
@token_required
def get_item_label_data(item_code):
    try:
        item = get_item_by_code(item_code)
        if not item:
            return jsonify({'message': 'Item not found'}), 404
            
        log_audit(
            action='label_data_fetched',
            details=f"Fetched label printing metadata for item '{item_code}'",
            performed_by_id=request.user['id'],
            performed_by_email=request.user['email'],
            entity_type='item',
            entity_id=str(item.get('id', '')),
            ip_address=request.remote_addr
        )
        return jsonify({
            'itemCode': item.get('itemCode'),
            'itemName': item.get('itemName'),
            'category': item.get('category'),
            'brand': item.get('brand'),
            'model': item.get('model'),
            'location': item.get('location'),
            'locationArea': item.get('locationArea'),
            'storageUnit': item.get('storageUnit'),
            'compartmentRow': item.get('compartmentRow'),
            'boxContainer': item.get('boxContainer'),
            'trackingMode': item.get('trackingMode'),
            'units': [
                {
                    'unitCode': u.get('unitCode'),
                    'serialNumber': u.get('serialNumber'),
                    'condition': u.get('condition'),
                    'status': u.get('status'),
                    'qrCodeUrl': u.get('qrCodeUrl')
                }
                for u in item.get('unitDetails', [])
            ],
            'qrCodeUrl': item.get('qrCodeUrl')
        }), 200
    except Exception as e:
        return jsonify({'message': f'Failed to fetch label data: {str(e)}'}), 500
