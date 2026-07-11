from flask import Blueprint, request, jsonify
from utils.jwt_helper import token_required, role_required
from services.audit_service import log_audit
from services.invoice_service import create_invoice_from_form, list_invoices, serialize_invoice

invoice_bp = Blueprint('invoice_bp', __name__)

@invoice_bp.route('', methods=['GET'])
@token_required
@role_required(['admin', 'store_head'])
def get_invoices():
    try:
        res = list_invoices(request.args)
        if 'page' in request.args:
            return jsonify({
                'items': res['invoices'],
                'pagination': res['pagination']
            }), 200
        else:
            return jsonify({'invoices': res['invoices']}), 200
    except Exception as e:
        return jsonify({'message': 'Failed to list invoices', 'error': str(e)}), 500

@invoice_bp.route('', methods=['POST'])
@token_required
@role_required(['admin', 'store_head'])
def create_invoice():
    try:
        data = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        invoice = create_invoice_from_form(data, request.files)
        
        log_audit(
            action='invoice_uploaded',
            details=f"Uploaded invoice '{invoice.get('invoiceNumber')}' from vendor '{invoice.get('vendor')}' for amount {invoice.get('totalAmount')}",
            performed_by_id=request.user['id'],
            performed_by_email=request.user['email'],
            entity_type='invoice',
            entity_id=str(invoice.get('_id', '')),
            new_value=serialize_invoice(invoice),
            ip_address=request.remote_addr
        )
        return jsonify({'message': 'Invoice created successfully', 'invoice': serialize_invoice(invoice)}), 201
    except Exception as e:
        return jsonify({'message': f'Failed to create invoice: {str(e)}'}), 500
