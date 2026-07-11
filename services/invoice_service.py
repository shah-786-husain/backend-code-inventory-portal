import os
from datetime import datetime
from bson import ObjectId
from utils.db import db
from services.storage_service import storage_service


def _to_float(value):
    try:
        return float(value) if value not in (None, '') else 0.0
    except ValueError:
        return 0.0


def _save_file(file_storage, entity_type, uploaded_by=None):
    if not file_storage or not file_storage.filename:
        return ''
    try:
        result = storage_service.upload_file(
            file_stream=file_storage.stream,
            original_filename=file_storage.filename,
            uploaded_by=uploaded_by,
            entity_type=entity_type
        )
        return f"/api/files/{result['fileId']}"
    except Exception as e:
        print(f"Failed to wrap legacy file upload for invoice: {e}")
        return ''


def create_invoice_from_form(form, files, uploaded_by=None):
    invoice_file_path = form.get('invoiceFilePath', '').strip()
    if not invoice_file_path:
        invoice_file_path = _save_file(files.get('invoiceFile'), 'invoice', uploaded_by)

    payment_proof_path = form.get('paymentProofPath', '').strip()
    if not payment_proof_path:
        payment_proof_path = _save_file(files.get('paymentProofFile'), 'payment_proof', uploaded_by)

    doc = {
        'invoiceNumber': form.get('invoiceNumber', '').strip(),
        'vendor': form.get('vendor', '').strip(),
        'purchaseDate': form.get('purchaseDate', '').strip(),
        'totalAmount': _to_float(form.get('invoiceTotalAmount')),
        'source': form.get('source', '').strip(),
        'invoiceFilePath': invoice_file_path,
        'paymentProofPath': payment_proof_path,
        'addedByEmail': form.get('addedByEmail', '').strip(),
        'createdAt': datetime.utcnow(),
        'updatedAt': datetime.utcnow(),
    }

    result = db.invoices.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc


def serialize_invoice(doc):
    return {
        '_id': str(doc.get('_id')),
        'id': str(doc.get('_id')),
        'invoiceNumber': doc.get('invoiceNumber', ''),
        'vendor': doc.get('vendor', ''),
        'purchaseDate': doc.get('purchaseDate', ''),
        'totalAmount': doc.get('totalAmount', 0),
        'source': doc.get('source', ''),
        'invoiceFilePath': doc.get('invoiceFilePath', ''),
        'paymentProofPath': doc.get('paymentProofPath', ''),
        'invoiceFileUrl': doc.get('invoiceFilePath', ''),
        'paymentProofUrl': doc.get('paymentProofPath', ''),
        'addedByEmail': doc.get('addedByEmail', ''),
        'createdAt': doc.get('createdAt').isoformat() if doc.get('createdAt') else '',
    }


def list_invoices(filters=None):
    import math
    filters = filters or {}
    query = {}
    
    search = (filters.get('search') or '').strip()
    if search:
        query['$or'] = [
            {'invoiceNumber': {'$regex': search, '$options': 'i'}},
            {'vendor': {'$regex': search, '$options': 'i'}}
        ]
        
    if filters.get('vendor'):
        query['vendor'] = {'$regex': filters.get('vendor'), '$options': 'i'}
    if filters.get('invoiceNumber'):
        query['invoiceNumber'] = filters.get('invoiceNumber')
        
    start_date = filters.get('startDate')
    end_date = filters.get('endDate')
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query['$gte'] = start_date
        if end_date:
            date_query['$lte'] = end_date
        query['purchaseDate'] = date_query
        
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
    
    sort_by = filters.get('sortBy', 'createdAt')
    sort_order = -1 if filters.get('sortOrder', 'desc').lower() == 'desc' else 1
    
    total = db.invoices.count_documents(query)
    docs = db.invoices.find(query).sort(sort_by, sort_order).skip(skip).limit(limit)
    invoices = [serialize_invoice(doc) for doc in docs]
    
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    
    return {
        'invoices': invoices,
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


def invoice_exists(invoice_id):
    if not invoice_id:
        return False
    try:
        return db.invoices.find_one({'_id': ObjectId(invoice_id)}) is not None
    except Exception:
        return False
