import io
from datetime import datetime
from utils.db import db

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

def _parse_date(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except Exception:
        try:
            # Try parsing YYYY-MM-DD
            return datetime.strptime(dt_str.strip(), '%Y-%m-%d')
        except Exception:
            return None

def get_inventory_report_data(filters=None):
    filters = filters or {}
    query = {}
    if filters.get('category'):
        query['category'] = filters.get('category')
    if filters.get('status'):
        query['status'] = filters.get('status')
    if filters.get('itemCode'):
        query['itemCode'] = filters.get('itemCode')
        
    items = list(db.items.find(query))
    formatted = []
    for item in items:
        qty = item.get('quantity', 0)
        price = item.get('unitPrice', 0)
        formatted.append({
            'itemCode': item.get('itemCode'),
            'itemName': item.get('itemName'),
            'category': item.get('category'),
            'subcategory': item.get('subcategory', ''),
            'itemType': item.get('itemType', ''),
            'quantity': qty,
            'availableQuantity': item.get('availableQuantity', 0),
            'issuedQuantity': item.get('issuedQuantity', 0),
            'unit': item.get('unit', 'pcs'),
            'unitPrice': price,
            'totalCost': qty * price,
            'location': item.get('location', ''),
            'status': item.get('status', 'Available')
        })
    return formatted

def get_purchase_report_data(filters=None):
    filters = filters or {}
    query = {}
    if filters.get('vendor'):
        query['vendor'] = {'$regex': filters.get('vendor'), '$options': 'i'}
    if filters.get('invoiceNumber'):
        query['invoiceNumber'] = filters.get('invoiceNumber')
        
    # Date filters on purchaseDate string (format YYYY-MM-DD)
    start_date = filters.get('startDate')
    end_date = filters.get('endDate')
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        query['purchaseDate'] = date_query
        
    invoices = list(db.invoices.find(query))
    formatted = []
    for inv in invoices:
        formatted.append({
            'invoiceNumber': inv.get('invoiceNumber'),
            'invoiceDate': inv.get('purchaseDate') or (inv.get('createdAt').strftime('%Y-%m-%d') if inv.get('createdAt') else ''),
            'vendor': inv.get('vendor'),
            'totalAmount': inv.get('totalAmount', 0),
            'source': inv.get('source', ''),
            'paymentStatus': inv.get('paymentStatus', 'Pending')
        })
    return formatted

def get_issued_items_report_data(filters=None):
    filters = filters or {}
    
    # Query transactions of type issue
    issue_query = {'transactionType': 'issue'}
    return_query = {'transactionType': 'return'}
    
    if filters.get('itemCode'):
        issue_query['itemCode'] = filters.get('itemCode')
        return_query['itemCode'] = filters.get('itemCode')
    if filters.get('issuedTo'):
        issue_query['issuedTo'] = filters.get('issuedTo')
    if filters.get('projectId'):
        issue_query['projectId'] = filters.get('projectId')
    if filters.get('deviceId'):
        issue_query['deviceId'] = filters.get('deviceId')
        
    start_date = _parse_date(filters.get('startDate'))
    end_date = _parse_date(filters.get('endDate'))
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        issue_query['timestamp'] = date_query
        return_query['timestamp'] = date_query
        
    issues = list(db.transactions.find(issue_query))
    returns = list(db.transactions.find(return_query))
    
    # Calculate outstanding balance per user + item SKU
    allocation_map = {}
    for tx in issues:
        key = (tx.get('issuedTo'), tx.get('itemCode'))
        qty = tx.get('quantity', 0)
        allocation_map[key] = allocation_map.get(key, 0) + qty
        
    for tx in returns:
        # A return actionByEmail matches the user returning the item
        key = (tx.get('actionByEmail'), tx.get('itemCode'))
        qty = tx.get('quantity', 0)
        if key in allocation_map:
            allocation_map[key] = max(0, allocation_map[key] - qty)
            
    formatted = []
    for (user_email, item_code), qty in allocation_map.items():
        if qty > 0:
            item = db.items.find_one({'itemCode': item_code})
            # Apply department filtering if requested (resolving user's department)
            if filters.get('department'):
                user_doc = db.users.find_one({'email': user_email})
                if not user_doc or user_doc.get('department') != filters.get('department'):
                    continue
                    
            formatted.append({
                'issuedTo': user_email,
                'itemCode': item_code,
                'itemName': item.get('itemName') if item else 'Unknown Item',
                'category': item.get('category') if item else '',
                'quantity': qty,
                'location': item.get('location') if item else 'Issued'
            })
    return formatted

def get_user_wise_report_data(filters=None):
    return get_issued_items_report_data(filters)

def get_project_wise_report_data(filters=None):
    filters = filters or {}
    tx_query = {
        'transactionType': {'$in': ['issue', 'consume']},
        'projectId': {'$ne': None}
    }
    
    if filters.get('projectId'):
        tx_query['projectId'] = filters.get('projectId')
    if filters.get('itemCode'):
        tx_query['itemCode'] = filters.get('itemCode')
        
    start_date = _parse_date(filters.get('startDate'))
    end_date = _parse_date(filters.get('endDate'))
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        tx_query['timestamp'] = date_query
        
    txs = list(db.transactions.find(tx_query))
    
    project_map = {}
    for tx in txs:
        key = (tx.get('projectId'), tx.get('itemCode'), tx.get('transactionType'))
        qty = tx.get('quantity', 0)
        project_map[key] = project_map.get(key, 0) + qty
        
    formatted = []
    for (project_id, item_code, tx_type), qty in project_map.items():
        item = db.items.find_one({'itemCode': item_code})
        formatted.append({
            'projectId': project_id,
            'itemCode': item_code,
            'itemName': item.get('itemName') if item else 'Unknown Item',
            'type': tx_type.upper(),
            'quantity': qty,
            'location': item.get('location') if item else ''
        })
    return formatted

def get_device_wise_report_data(filters=None):
    filters = filters or {}
    tx_query = {
        'transactionType': {'$in': ['issue', 'consume']},
        'deviceId': {'$ne': None}
    }
    
    if filters.get('deviceId'):
        tx_query['deviceId'] = filters.get('deviceId')
    if filters.get('itemCode'):
        tx_query['itemCode'] = filters.get('itemCode')
        
    start_date = _parse_date(filters.get('startDate'))
    end_date = _parse_date(filters.get('endDate'))
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        tx_query['timestamp'] = date_query
        
    txs = list(db.transactions.find(tx_query))
    
    device_map = {}
    for tx in txs:
        key = (tx.get('deviceId'), tx.get('itemCode'))
        qty = tx.get('quantity', 0)
        device_map[key] = device_map.get(key, 0) + qty
        
    formatted = []
    for (device_id, item_code), qty in device_map.items():
        item = db.items.find_one({'itemCode': item_code})
        formatted.append({
            'deviceId': device_id,
            'itemCode': item_code,
            'itemName': item.get('itemName') if item else 'Unknown Item',
            'quantity': qty,
            'category': item.get('category') if item else ''
        })
    return formatted

def get_low_stock_report_data(filters=None):
    filters = filters or {}
    query = {"status": {"$in": ["Low Stock", "Out of Stock", "low_stock", "out_of_stock"]}}
    if filters.get('category'):
        query['category'] = filters.get('category')
    if filters.get('itemCode'):
        query['itemCode'] = filters.get('itemCode')
        
    items = list(db.items.find(query))
    formatted = []
    for item in items:
        formatted.append({
            'itemCode': item.get('itemCode'),
            'itemName': item.get('itemName'),
            'category': item.get('category'),
            'availableQuantity': item.get('availableQuantity', 0),
            'quantity': item.get('quantity', 0),
            'status': item.get('status', 'Low Stock'),
            'location': item.get('location', '')
        })
    return formatted

def get_damaged_lost_report_data(filters=None):
    filters = filters or {}
    tx_query = {'transactionType': {'$in': ['damage', 'lost']}}
    
    if filters.get('itemCode'):
        tx_query['itemCode'] = filters.get('itemCode')
    if filters.get('type'):
        tx_query['transactionType'] = filters.get('type').lower()
        
    start_date = _parse_date(filters.get('startDate'))
    end_date = _parse_date(filters.get('endDate'))
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        tx_query['timestamp'] = date_query
        
    txs = list(db.transactions.find(tx_query))
    formatted = []
    for tx in txs:
        item = db.items.find_one({'itemCode': tx.get('itemCode')})
        formatted.append({
            'timestamp': tx.get('timestamp').isoformat() if tx.get('timestamp') else '',
            'itemCode': tx.get('itemCode'),
            'itemName': item.get('itemName') if item else 'Unknown Item',
            'type': tx.get('transactionType').upper(),
            'quantity': tx.get('quantity', 0),
            'remarks': tx.get('remarks', '')
        })
    return formatted

def get_invoice_report_data(filters=None):
    return get_purchase_report_data(filters)

def generate_export_file(report_type, export_format, filters=None):
    filters = filters or {}
    data = []
    
    if report_type == 'inventory':
        raw = get_inventory_report_data(filters)
        for r in raw:
            data.append({
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Category': r['category'],
                'Subcategory': r['subcategory'],
                'Type': r['itemType'],
                'Total Quantity': r['quantity'],
                'Available Quantity': r['availableQuantity'],
                'Issued Quantity': r['issuedQuantity'],
                'Unit': r['unit'],
                'Unit Price (INR)': r.get('unitPrice', 0),
                'Total Valuation': r.get('totalCost', 0),
                'Location': r['location'],
                'Status': r['status']
            })
            
    elif report_type == 'purchase':
        raw = get_purchase_report_data(filters)
        for r in raw:
            data.append({
                'Invoice Number': r['invoiceNumber'],
                'Purchase Date': r['invoiceDate'],
                'Vendor': r['vendor'],
                'Total Amount (INR)': r['totalAmount'],
                'Source': r['source'],
                'Payment Status': r['paymentStatus']
            })
            
    elif report_type == 'invoices':
        raw = get_invoice_report_data(filters)
        for r in raw:
            data.append({
                'Invoice Number': r['invoiceNumber'],
                'Invoice Date': r['invoiceDate'],
                'Vendor': r['vendor'],
                'Total Amount (INR)': r['totalAmount'],
                'Source': r['source'],
                'Payment Status': r['paymentStatus']
            })
            
    elif report_type == 'issued-items':
        raw = get_issued_items_report_data(filters)
        for r in raw:
            data.append({
                'Issued To': r['issuedTo'],
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Category': r['category'],
                'Quantity': r['quantity'],
                'Location': r['location']
            })
            
    elif report_type == 'low-stock':
        raw = get_low_stock_report_data(filters)
        for r in raw:
            data.append({
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Category': r['category'],
                'Available Quantity': r['availableQuantity'],
                'Total Quantity': r['quantity'],
                'Status': r['status'],
                'Location': r['location']
            })
            
    elif report_type == 'user-wise':
        raw = get_user_wise_report_data(filters)
        for r in raw:
            data.append({
                'Issued To': r['issuedTo'],
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Category': r['category'],
                'Quantity Assigned': r['quantity'],
                'Location': r['location']
            })
            
    elif report_type == 'project-wise':
        raw = get_project_wise_report_data(filters)
        for r in raw:
            data.append({
                'Project ID': r['projectId'],
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Type': r['type'],
                'Quantity': r['quantity'],
                'Location': r['location']
            })
            
    elif report_type == 'device-wise':
        raw = get_device_wise_report_data(filters)
        for r in raw:
            data.append({
                'Device ID': r['deviceId'],
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Quantity': r['quantity'],
                'Category': r['category']
            })

    elif report_type == 'damaged-lost':
        raw = get_damaged_lost_report_data(filters)
        for r in raw:
            data.append({
                'Timestamp': r['timestamp'],
                'Item Code': r['itemCode'],
                'Item Name': r['itemName'],
                'Type': r['type'],
                'Quantity': r['quantity'],
                'Remarks': r['remarks']
            })

    elif report_type == 'vendors':
        raw = get_vendor_report_data(filters)
        for r in raw:
            data.append({
                'Vendor Name': r['vendor'],
                'Total Spent (INR)': r['totalSpent'],
                'Invoice Count': r['invoiceCount'],
                'Catalog Items': r['itemCount'],
                'Active Repairs': r['activeMaintenanceCount'],
                'Completed Repairs': r['resolvedMaintenanceCount']
            })

    if export_format == 'excel':
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Report"
        if not data:
            ws.append(["Message"])
            ws.append(["No data found for the selected query"])
        else:
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([row.get(h) for h in headers])
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out, f"{report_type}_report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
    else:
        import csv
        out = io.StringIO()
        if not data:
            writer = csv.writer(out)
            writer.writerow(["Message"])
            writer.writerow(["No data found for the selected query"])
        else:
            headers = data[0].keys()
            writer = csv.DictWriter(out, fieldnames=headers)
            writer.writeheader()
            for r in data:
                writer.writerow(r)
        mem = io.BytesIO()
        mem.write(out.getvalue().encode('utf-8'))
        mem.seek(0)
        return mem, f"{report_type}_report_{datetime.utcnow().strftime('%Y%m%d')}.csv"

def get_vendor_report_data(filters=None):
    filters = filters or {}
    vendor_names = set()
    for name in db.invoices.distinct("vendor"):
        if name:
            vendor_names.add(name.strip())
    for name in db.items.distinct("vendor"):
        if name:
            vendor_names.add(name.strip())
    for name in db.maintenance_logs.distinct("vendor"):
        if name:
            vendor_names.add(name.strip())
            
    search_vendor = filters.get("vendor", "").strip()
    if search_vendor:
        vendor_names = {v for v in vendor_names if search_vendor.lower() in v.lower()}
        
    data = []
    for vendor in sorted(list(vendor_names)):
        invoice_stats = list(db.invoices.aggregate([
            {"$match": {"vendor": {"$regex": f"^{vendor}$", "$options": "i"}}},
            {"$group": {
                "_id": None,
                "totalSpent": {"$sum": "$totalAmount"},
                "invoiceCount": {"$sum": 1}
            }}
        ]))
        total_spent = invoice_stats[0]["totalSpent"] if invoice_stats else 0
        invoice_count = invoice_stats[0]["invoiceCount"] if invoice_stats else 0
        
        item_count = db.items.count_documents({"vendor": {"$regex": f"^{vendor}$", "$options": "i"}})
        
        active_repair_count = db.maintenance_logs.count_documents({
            "vendor": {"$regex": f"^{vendor}$", "$options": "i"},
            "status": "active"
        })
        resolved_repair_count = db.maintenance_logs.count_documents({
            "vendor": {"$regex": f"^{vendor}$", "$options": "i"},
            "status": "resolved"
        })
        
        data.append({
            "vendor": vendor,
            "totalSpent": round(total_spent, 2),
            "invoiceCount": invoice_count,
            "itemCount": item_count,
            "activeMaintenanceCount": active_repair_count,
            "resolvedMaintenanceCount": resolved_repair_count
        })
        
    return data

