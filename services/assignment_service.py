import os
from datetime import datetime
from bson import ObjectId
from utils.db import db
from services.audit_service import log_audit, get_dict_diff, sanitize_objids
from flask import has_request_context, request

def _get_ip():
    return request.remote_addr if has_request_context() else None

def _update_item_status(item):
    quantity = int(item.get('quantity', 0))
    issued_qty = int(item.get('issuedQuantity', 0))
    available_qty = int(item.get('availableQuantity', 0))
    
    try:
        min_limit = int(item.get('minLimits', 5))
    except (ValueError, TypeError):
        min_limit = 5
        
    status = 'Available'
    if quantity <= 0:
        status = 'Out of Stock'
    elif available_qty <= 0:
        if quantity > issued_qty:
            status = 'Maintenance'
        else:
            status = 'Issued' if issued_qty > 0 else 'Out of Stock'
    elif available_qty <= min_limit: # Threshold for low stock
        status = 'Low Stock'
    else:
        status = 'Available'
        
    db.items.update_one({'_id': item['_id']}, {'$set': {'status': status}})

    # Trigger notifications on low stock transition
    old_status = item.get('status')
    if status in ['Low Stock', 'Out of Stock'] and old_status != status:
        try:
            from services.notification_service import create_notification
            msg = f"Low stock alert: {item['itemName']} ({item['itemCode']}) status is now '{status}' ({available_qty} available)."
            create_notification(None, msg, "low_stock", f"/inventory/{item['itemCode']}", recipient_role="store_head")
            create_notification(None, msg, "low_stock", f"/inventory/{item['itemCode']}", recipient_role="admin")
        except Exception as e:
            print(f"Failed to trigger low stock notification: {e}")

def _update_serialized_units(item_code, unit_codes, new_status, new_condition=None):
    if not unit_codes:
        return
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        return
    
    unit_details = item.get('unitDetails', [])
    updated = False
    for unit in unit_details:
        if unit.get('unitCode') in unit_codes:
            unit['status'] = new_status
            if new_condition:
                unit['condition'] = new_condition
            updated = True
            
    if updated:
        db.items.update_one({'_id': item['_id']}, {'$set': {'unitDetails': unit_details}})

def _extract_common_metadata(data):
    meta = {}
    if 'projectId' in data and data['projectId']:
        meta['projectId'] = str(data['projectId']).strip()
    if 'deviceId' in data and data['deviceId']:
        meta['deviceId'] = str(data['deviceId']).strip()
    return meta

def issue_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    issued_to = data.get('issuedTo', '').strip()
    remarks = data.get('remarks', '').strip()
    expected_return_date = data.get('expectedReturnDate')
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0 or not issued_to:
        raise ValueError("itemCode, positive quantity, and issuedTo are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    avail_qty = int(item.get('availableQuantity', 0))
    if avail_qty < quantity:
        raise ValueError(f"Insufficient stock available. Current: {avail_qty}, Requested: {quantity}")
        
    # For serialized items, validate unit codes
    if item.get('trackingMode') == 'Serialized':
        if not unit_codes or len(unit_codes) != quantity:
            raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
        
        # Check if units are available in store
        unit_details = item.get('unitDetails', [])
        in_store_codes = {u['unitCode'] for u in unit_details if u['status'] == 'In Store'}
        for code in unit_codes:
            if code not in in_store_codes:
                raise ValueError(f"Unit '{code}' is not available in store (current status is not 'In Store')")
                
        _update_serialized_units(item_code, unit_codes, 'Issued')

    # Parse expected return date
    parsed_expected = None
    if expected_return_date:
        try:
            parsed_expected = datetime.fromisoformat(expected_return_date.replace('Z', '+00:00'))
        except Exception:
            pass

    # Perform update
    db.items.update_one(
        {'_id': item['_id']},
        {
            '$inc': {
                'availableQuantity': -quantity,
                'issuedQuantity': quantity
            },
            '$set': {'updatedAt': datetime.utcnow()}
        }
    )
    
    # Reload and update status
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    # Log transaction
    tx = {
        'transactionType': 'issue',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'issuedTo': issued_to,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'expectedReturnDate': parsed_expected,
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='item_issued', 
        details=f"Issued {quantity} of '{item_code}' to '{issued_to}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def return_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    remarks = data.get('remarks', '').strip()
    unit_codes = data.get('unitCodes', [])
    returned_condition = data.get('returnedCondition', 'Good').strip()
    actual_return_date = data.get('actualReturnDate')
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    issued_qty = int(item.get('issuedQuantity', 0))
    if issued_qty < quantity:
        raise ValueError(f"Cannot return {quantity} units. Only {issued_qty} units are currently issued.")
        
    # For serialized items, validate unit codes
    if item.get('trackingMode') == 'Serialized':
        if not unit_codes or len(unit_codes) != quantity:
            raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
            
        unit_details = item.get('unitDetails', [])
        issued_codes = {u['unitCode'] for u in unit_details if u['status'] == 'Issued'}
        for code in unit_codes:
            if code not in issued_codes:
                raise ValueError(f"Unit '{code}' is not marked as 'Issued'")
                
        _update_serialized_units(item_code, unit_codes, 'In Store', returned_condition)

    # Parse actual return date
    parsed_actual = datetime.utcnow()
    if actual_return_date:
        try:
            parsed_actual = datetime.fromisoformat(actual_return_date.replace('Z', '+00:00'))
        except Exception:
            pass

    # Perform update
    db.items.update_one(
        {'_id': item['_id']},
        {
            '$inc': {
                'availableQuantity': quantity,
                'issuedQuantity': -quantity
            },
            '$set': {'updatedAt': datetime.utcnow()}
        }
    )
    
    # Reload and update status
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    # Log transaction
    tx = {
        'transactionType': 'return',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'returnedCondition': returned_condition,
        'actualReturnDate': parsed_actual,
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='item_returned', 
        details=f"Returned {quantity} of '{item_code}' to store (Condition: {returned_condition})", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def consume_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    remarks = data.get('remarks', '').strip()
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    avail_qty = int(item.get('availableQuantity', 0))
    if avail_qty < quantity:
        raise ValueError(f"Insufficient stock available. Current: {avail_qty}, Requested: {quantity}")
        
    if item.get('trackingMode') == 'Serialized':
        if not unit_codes or len(unit_codes) != quantity:
            raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
            
        unit_details = item.get('unitDetails', [])
        in_store_codes = {u['unitCode'] for u in unit_details if u['status'] == 'In Store'}
        for code in unit_codes:
            if code not in in_store_codes:
                raise ValueError(f"Unit '{code}' is not available in store (cannot consume)")
                
        _update_serialized_units(item_code, unit_codes, 'Consumed')

    # Consumption permanently removes items from both total and available pools
    db.items.update_one(
        {'_id': item['_id']},
        {
            '$inc': {
                'quantity': -quantity,
                'availableQuantity': -quantity,
                'consumedQuantity': quantity
            },
            '$set': {'updatedAt': datetime.utcnow()}
        }
    )
    
    # Reload and update status
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    # Log transaction
    tx = {
        'transactionType': 'consume',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='stock_adjusted', 
        details=f"Consumed {quantity} of '{item_code}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def damage_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    damage_source = data.get('damageSource', 'available').strip() # 'available' or 'issued'
    remarks = data.get('remarks', '').strip()
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    if item.get('trackingMode') == 'Serialized':
        if not unit_codes or len(unit_codes) != quantity:
            raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
            
        unit_details = item.get('unitDetails', [])
        valid_status = 'In Store' if damage_source == 'available' else 'Issued'
        store_codes = {u['unitCode'] for u in unit_details if u['status'] == valid_status}
        for code in unit_codes:
            if code not in store_codes:
                raise ValueError(f"Unit '{code}' is not marked as '{valid_status}'")
                
        _update_serialized_units(item_code, unit_codes, 'Damaged')

    if damage_source == 'available':
        avail_qty = int(item.get('availableQuantity', 0))
        if avail_qty < quantity:
            raise ValueError(f"Insufficient available stock: {avail_qty}")
        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'quantity': -quantity,
                    'availableQuantity': -quantity,
                    'damagedQuantity': quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    elif damage_source == 'issued':
        issued_qty = int(item.get('issuedQuantity', 0))
        if issued_qty < quantity:
            raise ValueError(f"Insufficient issued stock: {issued_qty}")
        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'quantity': -quantity,
                    'issuedQuantity': -quantity,
                    'damagedQuantity': quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    else:
        raise ValueError("Invalid damageSource. Must be 'available' or 'issued'")
        
    # Reload and update status
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    # Log transaction
    tx = {
        'transactionType': 'damage',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': f"Source: {damage_source}. Remarks: {remarks}",
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='item_damaged', 
        details=f"Logged {quantity} damaged units of '{item_code}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def transfer_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    from_loc = data.get('fromLocation', '').strip()
    to_loc = data.get('toLocation', '').strip()
    remarks = data.get('remarks', '').strip()
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")

    # If project or device ID context is supplied, update location string accordingly
    project_id = data.get('projectId', '').strip()
    device_id = data.get('deviceId', '').strip()
    
    final_to_loc = to_loc
    if project_id:
        final_to_loc = f"Project: {project_id}"
    elif device_id:
        final_to_loc = f"Device: {device_id}"
        
    # Updates the item location permanently
    db.items.update_one(
        {'_id': item['_id']},
        {
            '$set': {
                'location': final_to_loc,
                'updatedAt': datetime.utcnow()
            }
        }
    )
    
    # Log transaction
    tx = {
        'transactionType': 'transfer',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'fromLocation': from_loc,
        'toLocation': final_to_loc,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    updated_item = db.items.find_one({'_id': item['_id']})
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='stock_adjusted', 
        details=f"Transferred '{item_code}' location from '{from_loc}' to '{final_to_loc}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def adjust_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0)) # Target total quantity
    available_quantity = int(data.get('availableQuantity', 0)) # Target available quantity
    remarks = data.get('remarks', '').strip()
    
    if not item_code:
        raise ValueError("itemCode is required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    if quantity < 0 or available_quantity < 0:
        raise ValueError("Quantities cannot be negative")
        
    # Update item pools directly
    db.items.update_one(
        {'_id': item['_id']},
        {
            '$set': {
                'quantity': quantity,
                'availableQuantity': available_quantity,
                'updatedAt': datetime.utcnow()
            }
        }
    )
    
    # Reload and update status
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    tx = {
        'transactionType': 'adjust',
        'itemCode': item_code,
        'quantity': quantity - item.get('quantity', 0), # difference
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'timestamp': datetime.utcnow()
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='stock_adjusted', 
        details=f"Stock adjustment for '{item_code}' (Total: {quantity}, Avail: {available_quantity})", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def lost_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    lost_from = data.get('lostFrom', 'available').strip() # 'available' or 'issued'
    remarks = data.get('remarks', '').strip()
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    if item.get('trackingMode') == 'Serialized':
        if not unit_codes or len(unit_codes) != quantity:
            raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
            
        unit_details = item.get('unitDetails', [])
        valid_status = 'In Store' if lost_from == 'available' else 'Issued'
        store_codes = {u['unitCode'] for u in unit_details if u['status'] == valid_status}
        for code in unit_codes:
            if code not in store_codes:
                raise ValueError(f"Unit '{code}' is not marked as '{valid_status}'")
                
        _update_serialized_units(item_code, unit_codes, 'Lost')

    if lost_from == 'available':
        avail_qty = int(item.get('availableQuantity', 0))
        if avail_qty < quantity:
            raise ValueError(f"Insufficient available stock: {avail_qty}")
        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'quantity': -quantity,
                    'availableQuantity': -quantity,
                    'lostQuantity': quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    elif lost_from == 'issued':
        issued_qty = int(item.get('issuedQuantity', 0))
        if issued_qty < quantity:
            raise ValueError(f"Insufficient issued stock: {issued_qty}")
        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'quantity': -quantity,
                    'issuedQuantity': -quantity,
                    'lostQuantity': quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    else:
        raise ValueError("Invalid lostFrom source. Must be 'available' or 'issued'")
        
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    tx = {
        'transactionType': 'lost',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': f"Source: {lost_from}. Remarks: {remarks}",
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='stock_adjusted', 
        details=f"Logged {quantity} lost units of '{item_code}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def repair_item_service(data, user):
    item_code = data.get('itemCode', '').strip()
    quantity = int(data.get('quantity', 0))
    repair_action = data.get('repairAction', 'send').strip() # 'send' or 'receive'
    remarks = data.get('remarks', '').strip()
    maintenance_vendor = data.get('maintenanceVendor', '').strip()
    unit_codes = data.get('unitCodes', [])
    
    if not item_code or quantity <= 0:
        raise ValueError("itemCode and positive quantity are required")
        
    item = db.items.find_one({'itemCode': item_code})
    if not item:
        raise ValueError("Item not found")
        
    if repair_action == 'send':
        avail_qty = int(item.get('availableQuantity', 0))
        if avail_qty < quantity:
            raise ValueError(f"Insufficient available stock to send to repair: {avail_qty}")
            
        if item.get('trackingMode') == 'Serialized':
            if not unit_codes or len(unit_codes) != quantity:
                raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
                
            unit_details = item.get('unitDetails', [])
            valid_codes = {u['unitCode'] for u in unit_details if u['status'] in ['In Store', 'Damaged']}
            for code in unit_codes:
                if code not in valid_codes:
                    raise ValueError(f"Unit '{code}' cannot be sent to repair (status is not 'In Store' or 'Damaged')")
                    
            _update_serialized_units(item_code, unit_codes, 'Under Repair')

        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'availableQuantity': -quantity,
                    'repairQuantity': quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    elif repair_action == 'receive':
        if item.get('trackingMode') == 'Serialized':
            if not unit_codes or len(unit_codes) != quantity:
                raise ValueError(f"For serialized items, you must specify exactly {quantity} unit code(s)")
                
            unit_details = item.get('unitDetails', [])
            repair_codes = {u['unitCode'] for u in unit_details if u['status'] == 'Under Repair'}
            for code in unit_codes:
                if code not in repair_codes:
                    raise ValueError(f"Unit '{code}' is not currently 'Under Repair'")
                    
            _update_serialized_units(item_code, unit_codes, 'In Store')

        db.items.update_one(
            {'_id': item['_id']},
            {
                '$inc': {
                    'availableQuantity': quantity,
                    'repairQuantity': -quantity
                },
                '$set': {'updatedAt': datetime.utcnow()}
            }
        )
    else:
        raise ValueError("Invalid repairAction. Must be 'send' or 'receive'")
        
    updated_item = db.items.find_one({'_id': item['_id']})
    _update_item_status(updated_item)
    
    tx = {
        'transactionType': 'repair',
        'itemCode': item_code,
        'quantity': quantity,
        'unitCodes': unit_codes,
        'repairAction': repair_action,
        'maintenanceVendor': maintenance_vendor,
        'actionBy': ObjectId(user['id']),
        'actionByEmail': user['email'],
        'remarks': remarks,
        'timestamp': datetime.utcnow(),
        **_extract_common_metadata(data)
    }
    db.transactions.insert_one(tx)
    
    old_val, new_val = get_dict_diff(item, updated_item)
    log_audit(
        action='stock_adjusted', 
        details=f"Logged repair '{repair_action}' for {quantity} of '{item_code}'", 
        performed_by_id=user['id'], 
        performed_by_email=user['email'],
        entity_type='item',
        entity_id=str(item['_id']),
        old_value=old_val,
        new_value=new_val,
        ip_address=_get_ip()
    )
    return tx

def list_transactions_service(filters, user):
    import math
    query = {}
    
    role = user.get('role', 'viewer')
    if role == 'team_member':
        query['issuedTo'] = user.get('email', '')
        
    if filters.get('transactionType'):
        query['transactionType'] = filters.get('transactionType')
    if filters.get('itemCode'):
        query['itemCode'] = filters.get('itemCode')
    if filters.get('issuedTo'):
        query['issuedTo'] = filters.get('issuedTo')
    if filters.get('projectId'):
        query['projectId'] = filters.get('projectId')
    if filters.get('deviceId'):
        query['deviceId'] = filters.get('deviceId')
        
    # Pagination
    try:
        page = max(1, int(filters.get('page', 1)))
    except Exception:
        page = 1
        
    try:
        limit = max(1, int(filters.get('limit', 20)))
    except Exception:
        limit = 20
        
    skip = (page - 1) * limit
    
    sort_by = filters.get('sortBy', 'timestamp')
    sort_order = -1 if filters.get('sortOrder', 'desc').lower() == 'desc' else 1
    
    total = db.transactions.count_documents(query)
    txs = list(db.transactions.find(query).sort(sort_by, sort_order).skip(skip).limit(limit))
    
    formatted = []
    for tx in txs:
        formatted.append({
            'id': str(tx['_id']),
            'transactionType': tx.get('transactionType'),
            'itemCode': tx.get('itemCode'),
            'quantity': tx.get('quantity', 0),
            'unitCodes': tx.get('unitCodes', []),
            'issuedTo': tx.get('issuedTo'),
            'fromLocation': tx.get('fromLocation'),
            'toLocation': tx.get('toLocation'),
            'projectId': tx.get('projectId'),
            'deviceId': tx.get('deviceId'),
            'expectedReturnDate': tx.get('expectedReturnDate').isoformat() if tx.get('expectedReturnDate') and hasattr(tx.get('expectedReturnDate'), 'isoformat') else str(tx.get('expectedReturnDate') or ''),
            'actualReturnDate': tx.get('actualReturnDate').isoformat() if tx.get('actualReturnDate') and hasattr(tx.get('actualReturnDate'), 'isoformat') else str(tx.get('actualReturnDate') or ''),
            'returnedCondition': tx.get('returnedCondition'),
            'maintenanceVendor': tx.get('maintenanceVendor'),
            'remarks': tx.get('remarks', ''),
            'timestamp': tx.get('timestamp').isoformat() if tx.get('timestamp') else ''
        })
        
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    
    return {
        'transactions': formatted,
        'total': total,
        'page': page,
        'limit': limit,
        'totalPages': total_pages,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': total_pages
        }
    }

def get_transaction_by_id_service(tx_id):
    try:
        tx = db.transactions.find_one({'_id': ObjectId(tx_id)})
    except Exception:
        return None
    if not tx:
        return None
        
    return {
        'id': str(tx['_id']),
        'transactionType': tx.get('transactionType'),
        'itemCode': tx.get('itemCode'),
        'quantity': tx.get('quantity', 0),
        'unitCodes': tx.get('unitCodes', []),
        'issuedTo': tx.get('issuedTo'),
        'fromLocation': tx.get('fromLocation'),
        'toLocation': tx.get('toLocation'),
        'projectId': tx.get('projectId'),
        'deviceId': tx.get('deviceId'),
        'expectedReturnDate': tx.get('expectedReturnDate').isoformat() if tx.get('expectedReturnDate') and hasattr(tx.get('expectedReturnDate'), 'isoformat') else str(tx.get('expectedReturnDate') or ''),
        'actualReturnDate': tx.get('actualReturnDate').isoformat() if tx.get('actualReturnDate') and hasattr(tx.get('actualReturnDate'), 'isoformat') else str(tx.get('actualReturnDate') or ''),
        'returnedCondition': tx.get('returnedCondition'),
        'maintenanceVendor': tx.get('maintenanceVendor'),
        'remarks': tx.get('remarks', ''),
        'timestamp': tx.get('timestamp').isoformat() if tx.get('timestamp') else ''
    }

def get_my_items_service(user):
    user_email = user.get('email', '')
    if not user_email:
        return []
        
    # Get all issues to this user
    issues = list(db.transactions.find({
        'transactionType': 'issue',
        'issuedTo': user_email
    }))
    
    # Get all returns from this user
    returns = list(db.transactions.find({
        'transactionType': 'return',
        'actionByEmail': user_email
    }))
    
    issued_map = {}
    for tx in issues:
        code = tx.get('itemCode')
        qty = tx.get('quantity', 0)
        issued_map[code] = issued_map.get(code, 0) + qty
        
    for tx in returns:
        code = tx.get('itemCode')
        qty = tx.get('quantity', 0)
        if code in issued_map:
            issued_map[code] = max(0, issued_map[code] - qty)
            
    my_items = []
    for code, outstanding_qty in issued_map.items():
        if outstanding_qty > 0:
            item = db.items.find_one({'itemCode': code})
            if item:
                my_items.append({
                    'itemCode': code,
                    'itemName': item.get('itemName', 'Unknown Item'),
                    'category': item.get('category', ''),
                    'quantity': outstanding_qty,
                    'location': item.get('location', 'Issued'),
                    'status': item.get('status', 'Issued'),
                    'brand': item.get('brand', ''),
                    'model': item.get('model', '')
                })
    return my_items

def get_user_items_service(user_id):
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
    except Exception:
        raise ValueError("Invalid user ID format")
    if not user:
        raise ValueError("User not found")
        
    return get_my_items_service(user)


def get_item_history_service(item_code):
    txs = list(db.transactions.find({'itemCode': item_code}).sort('timestamp', -1))
    
    formatted_txs = []
    for tx in txs:
        formatted_txs.append({
            'id': str(tx['_id']),
            'transactionType': tx.get('transactionType', ''),
            'itemCode': tx.get('itemCode', ''),
            'quantity': tx.get('quantity', 0),
            'unitCodes': tx.get('unitCodes', []),
            'fromLocation': tx.get('fromLocation'),
            'toLocation': tx.get('toLocation'),
            'projectId': tx.get('projectId'),
            'deviceId': tx.get('deviceId'),
            'issuedTo': tx.get('issuedTo'),
            'actionBy': str(tx.get('actionBy', '')),
            'remarks': tx.get('remarks', ''),
            'timestamp': tx['timestamp'].isoformat() if tx.get('timestamp') and hasattr(tx.get('timestamp'), 'isoformat') else str(tx.get('timestamp') or '')
        })
        
    # Also fetch audit logs for this item
    item = db.items.find_one({'itemCode': item_code})
    if item:
        item_id = str(item['_id'])
        audit_query = {
            '$or': [
                {'entityType': 'item', 'entityId': item_id},
                {'entityType': 'item', 'entityId': item_code}
            ],
            'action': {'$in': ['item_created', 'item_updated']}
        }
        logs = list(db.audit_logs.find(audit_query).sort('timestamp', -1))
        for log in logs:
            formatted_txs.append({
                'id': str(log['_id']),
                'transactionType': log.get('action', ''),
                'itemCode': item_code,
                'quantity': 0,
                'unitCodes': [],
                'fromLocation': '',
                'toLocation': '',
                'projectId': '',
                'deviceId': '',
                'issuedTo': '',
                'actionBy': log.get('performedByUsername', 'System'),
                'remarks': log.get('details', ''),
                'timestamp': log['timestamp'].isoformat() if log.get('timestamp') and hasattr(log.get('timestamp'), 'isoformat') else str(log.get('timestamp') or ''),
                'oldValue': sanitize_objids(log.get('oldValue')),
                'newValue': sanitize_objids(log.get('newValue'))
            })
            
    formatted_txs.sort(key=lambda x: x['timestamp'], reverse=True)
    return formatted_txs


def get_user_items_service(user_id):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise ValueError("Invalid user ID format")
        
    user = db.users.find_one({'_id': oid})
    if not user:
        raise ValueError("User not found")
        
    return get_my_items_service(user)
