from flask import Blueprint, request, jsonify, send_file
from utils.jwt_helper import token_required
from services.storage_service import storage_service
import traceback

file_bp = Blueprint('file_bp', __name__)

@file_bp.route('/upload', methods=['POST'])
@token_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"message": "No file part in the request"}), 400
        
    file_obj = request.files['file']
    if file_obj.filename == '':
        return jsonify({"message": "No file selected"}), 400
        
    entity_type = request.form.get('entityType', 'attachment')
    entity_id = request.form.get('entityId', None)
    
    try:
        result = storage_service.upload_file(
            file_stream=file_obj.stream,
            original_filename=file_obj.filename,
            uploaded_by=request.user['id'],
            entity_type=entity_type,
            entity_id=entity_id
        )
        return jsonify({
            "message": "File uploaded successfully",
            "file": result
        }), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    except Exception as e:
        print(f"File upload error: {traceback.format_exc()}")
        return jsonify({"message": "Internal server error during upload"}), 500

@file_bp.route('/<file_id>', methods=['GET'])
def get_file(file_id):
    try:
        # Extract user role from token if present in headers or query params
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        if not token and 'token' in request.args:
            token = request.args.get('token')

        user_role = None
        if token:
            try:
                from utils.jwt_helper import decode_token
                from utils.db import db
                from bson import ObjectId
                payload = decode_token(token)
                current_user = db.users.find_one({'_id': ObjectId(payload['user_id'])})
                if current_user and current_user.get('isActive', True):
                    role_val = current_user.get('role') or 'viewer'
                    user_role = role_val.lower().replace(' ', '_')
            except Exception:
                pass

        # Get metadata
        file_meta = storage_service.get_file_metadata(file_id)
        if not file_meta:
            return jsonify({"message": "File not found"}), 404
            
        entity_type = file_meta.get('linkedEntity', {}).get('entityType')
        
        # Access control based on entityType
        if entity_type in ['invoice', 'payment_proof']:
            if not user_role:
                return jsonify({"message": "Authentication required for this document type"}), 401
            if user_role not in ['admin', 'store_head']:
                return jsonify({"message": "Unauthorized access to this document type"}), 403
                
        # For item_image and attachment, any authenticated user can view (for now)
        
        # Get stream
        file_stream = storage_service.get_file_stream(file_meta['storagePath'])
        if not file_stream:
            return jsonify({"message": "File binary not found on storage"}), 404
            
        return send_file(
            file_stream,
            mimetype=file_meta['mimeType'],
            as_attachment=request.args.get('download', 'false').lower() == 'true',
            download_name=file_meta['filename']
        )
        
    except Exception as e:
        print(f"File retrieval error: {traceback.format_exc()}")
        return jsonify({"message": "Internal server error"}), 500
