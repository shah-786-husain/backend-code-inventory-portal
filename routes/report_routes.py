from flask import Blueprint, request, jsonify, send_file
from utils.jwt_helper import token_required, role_required
from services.audit_service import log_audit
from services.report_service import (
    get_inventory_report_data,
    get_purchase_report_data,
    get_issued_items_report_data,
    get_user_wise_report_data,
    get_project_wise_report_data,
    get_device_wise_report_data,
    get_low_stock_report_data,
    get_damaged_lost_report_data,
    get_invoice_report_data,
    get_vendor_report_data,
    generate_export_file
)

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/inventory", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer", "team_member"])
def get_inventory():
    try:
        filters = request.args.to_dict()
        data = get_inventory_report_data(filters)
        role = request.user.get('role')
        # Scrub financial data for team_member and viewer roles
        if role in ['team_member', 'viewer']:
            for item in data:
                item.pop('unitPrice', None)
                item.pop('totalCost', None)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/purchase", methods=["GET"])
@token_required
@role_required(["admin", "store_head"])
def get_purchase():
    try:
        filters = request.args.to_dict()
        data = get_purchase_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/issued-items", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer"])
def get_issued_items():
    try:
        filters = request.args.to_dict()
        data = get_issued_items_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/user-wise", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer"])
def get_user_wise():
    try:
        filters = request.args.to_dict()
        data = get_user_wise_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/project-wise", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer", "team_member"])
def get_project_wise():
    try:
        filters = request.args.to_dict()
        data = get_project_wise_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/device-wise", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer", "team_member"])
def get_device_wise():
    try:
        filters = request.args.to_dict()
        data = get_device_wise_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/low-stock", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer", "team_member"])
def get_low_stock():
    try:
        filters = request.args.to_dict()
        data = get_low_stock_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/damaged-lost", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer"])
def get_damaged_lost():
    try:
        filters = request.args.to_dict()
        data = get_damaged_lost_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/invoices", methods=["GET"])
@token_required
@role_required(["admin", "store_head"])
def get_invoices():
    try:
        filters = request.args.to_dict()
        data = get_invoice_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/vendors", methods=["GET"])
@token_required
@role_required(["admin", "store_head", "viewer"])
def get_vendors():
    try:
        filters = request.args.to_dict()
        data = get_vendor_report_data(filters)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@reports_bp.route("/export", methods=["GET"])
@token_required
@role_required(["admin", "store_head"])
def export_file():
    report_type = request.args.get("type", "inventory").strip()
    export_format = request.args.get("format", "csv").strip()
    filters = request.args.to_dict()
    
    # Clean up non-filter params
    filters.pop('type', None)
    filters.pop('format', None)
    
    try:
        file_stream, filename = generate_export_file(report_type, export_format, filters)
        
        mimetype = "text/csv"
        if export_format == "excel":
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
        # Log export transaction to audit trail
        log_audit(
            "report_exported", 
            f"Exported '{report_type}' report in {export_format.upper()} format", 
            request.user["id"], 
            request.user["email"]
        )
        
        return send_file(
            file_stream,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"message": "Failed to generate export file", "error": str(e)}), 500
