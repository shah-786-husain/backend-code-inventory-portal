import json
import os
import io
from datetime import datetime
from bson import ObjectId
from utils.db import db

try:
    import qrcode
    import qrcode.image.svg
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
from services.invoice_service import create_invoice_from_form
from services.storage_service import storage_service


def _to_float(value):
    try:
        return float(value) if value not in (None, '') else 0.0
    except Exception:
        return 0.0


def _to_int(value, default=1):
    try:
        return max(1, int(value))
    except Exception:
        return default


def _save_file(file_storage, entity_type, uploaded_by=None):
    if not file_storage or not file_storage.filename:
        return ''
        
    try:
        # Wrap old upload flow inside the new secure storage_service
        result = storage_service.upload_file(
            file_stream=file_storage.stream,
            original_filename=file_storage.filename,
            uploaded_by=uploaded_by,
            entity_type=entity_type
        )
        # Return the secure URL format
        return f"/api/files/{result['fileId']}"
    except Exception as e:
        print(f"Failed to wrap legacy file upload: {e}")
        return ''



def _short_code(text, fallback='GEN'):
    text = (text or '').strip()
    if not text:
        return fallback

    cleaned = ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in text.upper())
    words = [w for w in cleaned.split() if w]
    if not words:
        return fallback

    ignore_words = {'AND', 'OR', 'THE', 'FOR', 'WITH', 'OF', 'IN'}
    words = [w for w in words if w not in ignore_words]
    if not words:
        return fallback

    if len(words) == 1:
        return words[0][:3].ljust(3, 'X')

    return ''.join(w[0] for w in words[:3])[:3]


def _build_item_prefix(category, item_type, item_name, subcategory=''):
    text = f'{category} {subcategory} {item_type} {item_name}'.lower()

    # Common iRAMA / lab inventory codes
    smart_rules = [
        (('jetson', 'orin'), 'JET-ORN'),
        (('jetson', 'nano'), 'JET-NAN'),
        (('camera', 'usb'), 'CAM-USB'),
        (('mokose',), 'CAM-USB'),
        (('gps', 'usb'), 'GPS-USB'),
        (('gps',), 'GPS-MOD'),
        (('power bank',), 'PWR-PB'),
        (('inverter',), 'PWR-INV'),
        (('usb hub',), 'HUB-USB'),
        (('display',), 'DSP-HDM'),
        (('screen',), 'DSP-HDM'),
        (('keyboard', 'bluetooth'), 'KEY-BT'),
        (('keyboard',), 'KEY-BRD'),
        (('mouse',), 'MSE-WRL'),
        (('usb extension',), 'CAB-USB'),
        (('usb cable',), 'CAB-USB'),
        (('cable',), 'CAB-GEN'),
        (('glue gun',), 'TOOL-GLU'),
        (('glue stick',), 'ADH-GLU'),
        (('adhesive',), 'ADH-GLU'),
        (('fevicol',), 'ADH-GLU'),
        (('connector',), 'CON-GEN'),
        (('socket',), 'CON-PWR'),
        (('plug',), 'CON-PWR'),
        (('mount',), 'MNT-GEN'),
        (('suction',), 'MNT-SUC'),
        (('accessory',), 'ACC-GEN'),
    ]

    for keywords, prefix in smart_rules:
        if all(keyword in text for keyword in keywords):
            return prefix

    cat_code = _short_code(category, 'GEN')
    type_code = _short_code(item_type or subcategory or item_name, 'ITM')
    return f'{cat_code}-{type_code}'


def _next_item_code(prefix):
    # Atomic counter. One running series for each prefix.
    counter = db.counters.find_one_and_update(
        {'_id': f'item_code_{prefix}'},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=True,
    )
    return f'{prefix}-{counter["seq"]:03d}'


def generate_item_code(category, item_type, item_name, subcategory=''):
    prefix = _build_item_prefix(category, item_type, item_name, subcategory)
    return _next_item_code(prefix)



def suggest_item_code(category, item_type, item_name='', subcategory=''):
    """Generate a fresh suggested item code from category/type/name.

    This uses the same counter system as new item creation, so the suggested
    code will be unique. It is used only when the user clicks "Suggest New Code".
    Existing item codes are never changed automatically.
    """
    return generate_item_code(category, item_type, item_name, subcategory)


def _ensure_item_code_is_unique(item_code, current_item_id=None):
    if not item_code:
        return

    query = {'itemCode': item_code}
    if current_item_id:
        query['_id'] = {'$ne': ObjectId(current_item_id)}

    existing = db.items.find_one(query)
    if existing:
        raise ValueError('This item code already exists. Please use another item code.')


def _normalize_unit_details(unit_details, base_item_code, quantity, tracking_mode):
    if tracking_mode != 'Serialized':
        return []

    normalized = []
    for index in range(quantity):
        source = unit_details[index] if index < len(unit_details) and isinstance(unit_details[index], dict) else {}
        unit_code = source.get('unitCode', '').strip()

        # Replace frontend placeholders like ITEM-01 or blank with backend final code.
        if not unit_code or unit_code.startswith('ITEM'):
            unit_code = f'{base_item_code}-{index + 1:02d}'

        normalized.append({
            'unitCode': unit_code,
            'serialNumber': source.get('serialNumber', '').strip(),
            'condition': source.get('condition', 'New').strip() or 'New',
            'status': source.get('status', 'In Store').strip() or 'In Store',
            'remarks': source.get('remarks', '').strip(),
        })

    return normalized


def create_item_from_form(form, files):
    invoice_mode = form.get('invoiceMode', 'new')
    invoice_record_id = form.get('invoiceRecordId', '').strip()

    if invoice_mode == 'new' and (form.get('invoiceNumber') or files.get('invoiceFile')):
        invoice_doc = create_invoice_from_form(form, files)
        invoice_record_id = str(invoice_doc['_id'])

    try:
        unit_details = json.loads(form.get('unitDetails', '[]'))
    except Exception:
        unit_details = []

    quantity = _to_int(form.get('quantity'))
    tracking_mode = form.get('trackingMode', 'Bulk')

    # Item code is optional in frontend. If blank, backend creates final code.
    item_code = form.get('itemCode', '').strip()
    if not item_code:
        item_code = generate_item_code(
            form.get('category', ''),
            form.get('itemType', ''),
            form.get('itemName', ''),
            form.get('subcategory', ''),
        )
    else:
        _ensure_item_code_is_unique(item_code)

    unit_details = _normalize_unit_details(unit_details, item_code, quantity, tracking_mode)
    
    # Check if frontend passed imageUrl explicitly (new Phase 7 flow)
    item_image_path = form.get('imageUrl', '').strip()
    if not item_image_path:
        # Fallback to legacy file upload (wrapped via storage_service)
        item_image_path = _save_file(files.get('itemImage'), 'item_image')

    issued_qty = 0
    available_qty = quantity
    status = 'Available' if quantity > 0 else 'Out of Stock'

    doc = {
        'itemCode': item_code,
        'itemName': form.get('itemName', '').strip(),
        'category': form.get('category', '').strip(),
        'subcategory': form.get('subcategory', '').strip(),
        'itemType': form.get('itemType', '').strip(),
        'trackingMode': tracking_mode,
        'quantity': quantity,
        'availableQuantity': available_qty,
        'issuedQuantity': issued_qty,
        'unit': form.get('unit', 'pcs').strip() or 'pcs',
        'brand': form.get('brand', '').strip(),
        'model': form.get('model', '').strip(),
        'location': form.get('location', '').strip(),
        'locationCode': form.get('location', '').strip() if len(form.get('location', '').strip().split("-")) >= 5 else None,
        'locationArea': f"{form.get('location', '').strip().split('-')[0]} - {form.get('location', '').strip().split('-')[1]}" if len(form.get('location', '').strip().split("-")) >= 5 else form.get('locationArea', '').strip(),
        'storageUnit': form.get('location', '').strip().split('-')[2] if len(form.get('location', '').strip().split("-")) >= 5 else form.get('storageUnit', '').strip(),
        'compartmentRow': form.get('location', '').strip().split('-')[3] if len(form.get('location', '').strip().split("-")) >= 5 else form.get('compartmentRow', '').strip(),
        'boxContainer': form.get('location', '').strip().split('-')[4] if len(form.get('location', '').strip().split("-")) >= 5 else form.get('boxContainer', '').strip(),
        'locationNotes': form.get('locationNotes', '').strip(),
        'source': form.get('source', '').strip(),
        'ownership': form.get('ownership', '').strip(),
        'returnPolicy': form.get('returnPolicy', '').strip(),
        'purchaseDate': form.get('purchaseDate', '').strip(),
        'unitPrice': _to_float(form.get('unitPrice')),
        'shippingCost': _to_float(form.get('shippingCost')),
        'taxAmount': _to_float(form.get('taxAmount')),
        'otherCost': _to_float(form.get('otherCost')),
        'totalCost': _to_float(form.get('totalCost')),
        'effectiveUnitCost': _to_float(form.get('effectiveUnitCost')),
        'vendor': form.get('vendor', '').strip(),
        'invoiceNumber': form.get('invoiceNumber', '').strip(),
        'invoiceRecordId': invoice_record_id,
        'remarks': form.get('remarks', '').strip(),
        'unitDetails': unit_details,
        'itemImagePath': item_image_path,
        'addedByEmail': form.get('addedByEmail', '').strip(),
        'addedAt': form.get('addedAt', '').strip(),
        'status': status,
        'createdAt': datetime.utcnow(),
        'updatedAt': datetime.utcnow(),
    }

    result = db.items.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc


def _iso_date(value):
    return value.isoformat() if hasattr(value, 'isoformat') else (value or '')


def serialize_item(doc):
    item_code = doc.get('itemCode', '')
    return {
        '_id': str(doc.get('_id')),
        'id': str(doc.get('_id')),
        'itemCode': item_code,
        'itemName': doc.get('itemName', ''),
        'category': doc.get('category', ''),
        'subcategory': doc.get('subcategory', ''),
        'itemType': doc.get('itemType', ''),
        'trackingMode': doc.get('trackingMode', ''),
        'quantity': doc.get('quantity', 0),
        'availableQuantity': doc.get('availableQuantity', 0),
        'availableQty': doc.get('availableQuantity', 0),
        'issuedQuantity': doc.get('issuedQuantity', 0),
        'issuedQty': doc.get('issuedQuantity', 0),
        'unit': doc.get('unit', ''),
        'brand': doc.get('brand', ''),
        'model': doc.get('model', ''),
        'location': doc.get('location', ''),
        'locationArea': doc.get('locationArea', ''),
        'storageUnit': doc.get('storageUnit', ''),
        'compartmentRow': doc.get('compartmentRow', ''),
        'boxContainer': doc.get('boxContainer', ''),
        'locationNotes': doc.get('locationNotes', ''),
        'source': doc.get('source', ''),
        'ownership': doc.get('ownership', ''),
        'returnPolicy': doc.get('returnPolicy', ''),
        'purchaseDate': doc.get('purchaseDate', ''),
        'unitPrice': doc.get('unitPrice', 0),
        'shippingCost': doc.get('shippingCost', 0),
        'taxAmount': doc.get('taxAmount', 0),
        'otherCost': doc.get('otherCost', 0),
        'totalCost': doc.get('totalCost', 0),
        'effectiveUnitCost': doc.get('effectiveUnitCost', 0),
        'vendor': doc.get('vendor', ''),
        'invoiceNumber': doc.get('invoiceNumber', ''),
        'invoiceRecordId': doc.get('invoiceRecordId', ''),
        'remarks': doc.get('remarks', ''),
        'unitDetails': [
            {
                **u,
                'qrCodeUrl': f"/api/items/qr?code={u.get('unitCode', '')}"
            }
            for u in doc.get('unitDetails', [])
        ],
        'qrCodeUrl': f"/api/items/qr?code={item_code}",
        'itemImagePath': doc.get('itemImagePath', ''),
        'imageUrl': doc.get('itemImagePath', ''),
        'addedByEmail': doc.get('addedByEmail', ''),
        'status': doc.get('status', ''),
        'createdAt': _iso_date(doc.get('createdAt')),
        'updatedAt': _iso_date(doc.get('updatedAt')),
    }


def _build_query(args):
    query = {}
    search = (args.get('search') or '').strip()
    category = (args.get('category') or '').strip()
    item_type = (args.get('itemType') or '').strip()
    status = (args.get('status') or '').strip()
    location = (args.get('location') or '').strip()
    ownership = (args.get('ownership') or '').strip()
    vendor = (args.get('vendor') or '').strip()

    if search:
        query['$or'] = [
            {'itemName': {'$regex': search, '$options': 'i'}},
            {'itemCode': {'$regex': search, '$options': 'i'}},
            {'brand': {'$regex': search, '$options': 'i'}},
            {'model': {'$regex': search, '$options': 'i'}},
            {'location': {'$regex': search, '$options': 'i'}},
        ]
    if category:
        query['category'] = category
    if item_type:
        query['itemType'] = item_type
    if status:
        query['status'] = {'$regex': f'^{status}$', '$options': 'i'}
    if location:
        query['location'] = {'$regex': location, '$options': 'i'}
    if ownership:
        query['ownership'] = {'$regex': ownership, '$options': 'i'}
    if vendor:
        query['vendor'] = {'$regex': vendor, '$options': 'i'}

    return query


def list_items(args=None):
    import math
    args = args or {}
    query = _build_query(args)
    
    # Parse pagination params
    try:
        page = max(1, int(args.get('page', 1)))
    except Exception:
        page = 1
        
    try:
        limit = max(1, int(args.get('limit', 10)))
    except Exception:
        limit = 10
        
    skip = (page - 1) * limit
    
    # Sorting fields
    sort_by = args.get('sortBy', 'createdAt')
    sort_order = -1 if args.get('sortOrder', 'desc').lower() == 'desc' else 1
    
    total = db.items.count_documents(query)
    docs = db.items.find(query).sort(sort_by, sort_order).skip(skip).limit(limit)
    items = [serialize_item(doc) for doc in docs]
    
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    
    return {
        'items': items,
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


def get_item(item_id):
    doc = None
    if ObjectId.is_valid(item_id):
        try:
            doc = db.items.find_one({'_id': ObjectId(item_id)})
        except Exception:
            pass
    if not doc:
        doc = db.items.find_one({'itemCode': item_id})
    return serialize_item(doc) if doc else None


def get_inventory_options():
    return {
        'categories': sorted([x for x in db.items.distinct('category') if x]),
        'itemTypes': sorted([x for x in db.items.distinct('itemType') if x]),
        'statuses': sorted([x for x in db.items.distinct('status') if x]),
    }



def _build_location_from_form(form):
    parts = [
        form.get('locationArea', '').strip(),
        form.get('storageUnit', '').strip(),
        form.get('compartmentRow', '').strip(),
        form.get('boxContainer', '').strip(),
    ]
    return ' / '.join([p for p in parts if p])


def update_item_from_form(item_id, form, files):
    """Update an existing item.

    Important: itemCode is not regenerated here because it may already be written
    physically on the item/rack label.
    """
    existing = None
    if ObjectId.is_valid(item_id):
        try:
            existing = db.items.find_one({'_id': ObjectId(item_id)})
        except Exception:
            pass
    if not existing:
        existing = db.items.find_one({'itemCode': item_id})
    if not existing:
        return None
    object_id = existing['_id']

    try:
        unit_details = json.loads(form.get('unitDetails', '[]'))
    except Exception:
        unit_details = existing.get('unitDetails', [])

    old_quantity = _to_int(existing.get('quantity', 1))
    quantity = _to_int(form.get('quantity', old_quantity), old_quantity)
    issued_qty = int(existing.get('issuedQuantity', 0) or 0)
    available_qty = max(quantity - issued_qty, 0)
    tracking_mode = form.get('trackingMode', existing.get('trackingMode', 'Bulk'))

    # Force itemCode to be immutable after creation
    item_code = existing.get('itemCode', '')

    # Only normalize unit details when the item is serialized.
    # For existing units, keep provided serial numbers/status/remarks.
    if tracking_mode == 'Serialized':
        unit_details = _normalize_unit_details(unit_details, item_code, quantity, tracking_mode)
    else:
        unit_details = []

    new_image_path = form.get('imageUrl', '').strip()
    if not new_image_path and files.get('itemImage'):
        new_image_path = _save_file(files.get('itemImage'), 'item_image')
        
    item_image_path = new_image_path or existing.get('itemImagePath', '')

    location_from_parts = _build_location_from_form(form)
    location = form.get('location', '').strip() or location_from_parts or existing.get('location', '')

    status = existing.get('status', 'Available')
    if quantity <= 0:
        status = 'Out of Stock'
    elif available_qty <= 0:
        status = 'Issued' if issued_qty > 0 else 'Out of Stock'
    else:
        status = 'Available'

    update_doc = {
        'itemCode': item_code,
        'itemName': form.get('itemName', existing.get('itemName', '')).strip(),
        'category': form.get('category', existing.get('category', '')).strip(),
        'subcategory': form.get('subcategory', existing.get('subcategory', '')).strip(),
        'itemType': form.get('itemType', existing.get('itemType', '')).strip(),
        'trackingMode': tracking_mode,
        'quantity': quantity,
        'availableQuantity': available_qty,
        'unit': form.get('unit', existing.get('unit', 'pcs')).strip() or 'pcs',
        'brand': form.get('brand', existing.get('brand', '')).strip(),
        'model': form.get('model', existing.get('model', '')).strip(),
        'location': location,
        'locationCode': location if len(location.split("-")) >= 5 else existing.get('locationCode'),
        'locationArea': f"{location.split('-')[0]} - {location.split('-')[1]}" if len(location.split("-")) >= 5 else form.get('locationArea', existing.get('locationArea', '')).strip(),
        'storageUnit': location.split('-')[2] if len(location.split("-")) >= 5 else form.get('storageUnit', existing.get('storageUnit', '')).strip(),
        'compartmentRow': location.split('-')[3] if len(location.split("-")) >= 5 else form.get('compartmentRow', existing.get('compartmentRow', '')).strip(),
        'boxContainer': location.split('-')[4] if len(location.split("-")) >= 5 else form.get('boxContainer', existing.get('boxContainer', '')).strip(),
        'locationNotes': form.get('locationNotes', existing.get('locationNotes', '')).strip(),
        'source': form.get('source', existing.get('source', '')).strip(),
        'ownership': form.get('ownership', existing.get('ownership', '')).strip(),
        'returnPolicy': form.get('returnPolicy', existing.get('returnPolicy', '')).strip(),
        'purchaseDate': form.get('purchaseDate', existing.get('purchaseDate', '')).strip(),
        'unitPrice': _to_float(form.get('unitPrice', existing.get('unitPrice', 0))),
        'shippingCost': _to_float(form.get('shippingCost', existing.get('shippingCost', 0))),
        'taxAmount': _to_float(form.get('taxAmount', existing.get('taxAmount', 0))),
        'otherCost': _to_float(form.get('otherCost', existing.get('otherCost', 0))),
        'totalCost': _to_float(form.get('totalCost', existing.get('totalCost', 0))),
        'effectiveUnitCost': _to_float(form.get('effectiveUnitCost', existing.get('effectiveUnitCost', 0))),
        'vendor': form.get('vendor', existing.get('vendor', '')).strip(),
        'invoiceNumber': form.get('invoiceNumber', existing.get('invoiceNumber', '')).strip(),
        'remarks': form.get('remarks', existing.get('remarks', '')).strip(),
        'unitDetails': unit_details,
        'itemImagePath': item_image_path,
        'status': status,
        'updatedAt': datetime.utcnow(),
    }

    db.items.update_one({'_id': object_id}, {'$set': update_doc})
    updated = db.items.find_one({'_id': object_id})
    return serialize_item(updated)


def get_item_by_code(item_code):
    doc = db.items.find_one({'itemCode': item_code})
    return serialize_item(doc) if doc else None


def generate_qr_svg(data):
    """Generates a QR Code in SVG format for the given code.
    If the qrcode library is not installed, it yields a valid vector placeholder SVG.
    """
    if QRCODE_AVAILABLE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            factory = qrcode.image.svg.SvgPathImage
            img = qr.make_image(image_factory=factory)
            output = io.BytesIO()
            img.save(output)
            return output.getvalue().decode('utf-8')
        except Exception as e:
            print(f"qrcode library failed to generate SVG: {e}")
            
    # Inline clean vector SVG fallback representation
    placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
        <rect width="200" height="200" fill="#1e293b" rx="10"/>
        <rect x="20" y="20" width="160" height="160" fill="none" stroke="#6366f1" stroke-width="4" stroke-dasharray="10 5"/>
        <text x="100" y="90" font-family="sans-serif" font-size="12" fill="#94a3b8" text-anchor="middle" font-weight="bold">QR CODE PLACEHOLDER</text>
        <text x="100" y="115" font-family="monospace" font-size="10" fill="#f8fafc" text-anchor="middle">{data}</text>
        <text x="100" y="145" font-family="sans-serif" font-size="8" fill="#ef4444" text-anchor="middle">(qrcode library not installed)</text>
    </svg>'''
    return placeholder

