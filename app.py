import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from utils.db import init_db
from utils.errors import register_error_handlers
from utils.jwt_helper import token_required

# Import blueprints
from routes.auth_routes import auth_bp
from routes.user_routes import user_bp as users_bp
from routes.item_routes import item_bp as inventory_bp
from routes.assignment_routes import assignment_bp as transactions_bp
from routes.invoice_routes import invoice_bp as invoices_bp
from routes.dashboard_routes import dashboard_bp
from routes.report_routes import reports_bp
from routes.audit_routes import audit_bp
from routes.search_routes import search_bp
from routes.file_routes import file_bp
from routes.asset_request_routes import asset_request_bp
from routes.notification_routes import notification_bp
from routes.approval_routes import approval_bp
from routes.location_routes import location_bp
from routes.maintenance_routes import maintenance_bp
from routes.vendor_routes import vendor_bp


import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    log_level = logging.INFO if not app.config.get('DEBUG', False) else logging.DEBUG
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s [%(pathname)s:%(lineno)d]: %(message)s'
    )
    
    # Console logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    app.logger.addHandler(console_handler)
    
    # File logging in production
    if not app.config.get('DEBUG', False):
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, 'inventory_portal.log'),
                maxBytes=10 * 1024 * 1024, # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
        except Exception as e:
            app.logger.error(f"Failed to configure file logging: {e}")
            
    app.logger.setLevel(log_level)
    app.logger.info("iRAMA Inventory System Logging initialized.")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize Logging
    setup_logging(app)

    # Enable CORS for frontend (Vite dev server on port 5173) and production
    origins = "*" if app.config.get('DEBUG', True) else os.getenv("ALLOWED_ORIGINS", "*")
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    # Initialize Database
    init_db()

    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(inventory_bp, url_prefix='/api/items')
    app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
    app.register_blueprint(invoices_bp, url_prefix='/api/invoices')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(audit_bp, url_prefix='/api/audit-logs')
    app.register_blueprint(search_bp, url_prefix='/api/search')
    app.register_blueprint(file_bp, url_prefix='/api/files')
    app.register_blueprint(asset_request_bp, url_prefix='/api/asset-requests')
    app.register_blueprint(notification_bp, url_prefix='/api/notifications')
    app.register_blueprint(approval_bp, url_prefix='/api/approvals')
    app.register_blueprint(location_bp, url_prefix='/api/locations')
    app.register_blueprint(maintenance_bp, url_prefix='/api/maintenance')
    app.register_blueprint(vendor_bp, url_prefix='/api/vendors')

    # Health check endpoint
    @app.route('/')
    def index():
        return jsonify({
            'status': 'healthy',
            'service': 'Inventory & Asset Management API Portal',
            'version': '1.0.0'
        }), 200

    # Debug database helper endpoint - locked in production mode
    @app.route('/api/debug/db')
    def debug_db():
        from config import Config
        if Config.ENV == 'production':
            return jsonify({
                "success": False,
                "message": "Debug route is disabled in production",
                "errorCode": "FORBIDDEN",
                "details": None
            }), 403
            
        try:
            from utils.db import db
            stats = {}
            for col in db.list_collection_names():
                stats[col] = db[col].count_documents({})
            return jsonify({
                "success": True,
                "collections": stats
            }), 200
        except Exception as e:
            return jsonify({
                "success": False,
                "message": "Failed to query database state",
                "errorCode": "INTERNAL_ERROR",
                "details": str(e)
            }), 500

    # Validate JWT secret in production (debug false)
    if not app.config.get('DEBUG') and app.config.get('JWT_SECRET') == 'super-secret-inventory-key-change-in-prod':
        raise RuntimeError('JWT_SECRET must be changed from the default in production')

    # Register global error handlers
    register_error_handlers(app)

    return app

app = create_app()

if __name__ == '__main__':
    # Ensure upload folder exists
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
