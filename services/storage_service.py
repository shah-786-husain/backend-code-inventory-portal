import os
import uuid
from io import BytesIO
import magic
from config import Config
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

class StorageProvider:
    def save_file(self, file_stream, destination_path):
        raise NotImplementedError
    def get_file_stream(self, storage_path):
        raise NotImplementedError
    def generate_download_url(self, storage_path, expires_in):
        raise NotImplementedError
    def delete_file(self, storage_path):
        raise NotImplementedError

class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir):
        self.base_dir = os.path.abspath(base_dir)
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

    def _safe_path(self, path):
        # Reject absolute paths
        if os.path.isabs(path) or path.startswith("/") or path.startswith("\\"):
            raise ValueError("Path traversal attempt detected.")
            
        # Normalize and remove any leading path separators
        norm_path = os.path.normpath(path).lstrip(os.sep + (os.altsep or ''))
        # Prevent any path traversal sequences
        if norm_path.startswith("..") or ".." in norm_path.split(os.sep):
            raise ValueError("Path traversal attempt detected.")
        full_path = os.path.abspath(os.path.join(self.base_dir, norm_path))
        if not full_path.startswith(self.base_dir):
            raise ValueError("Path traversal attempt detected.")
        return full_path

    def save_file(self, file_stream, destination_path):
        full_path = self._safe_path(destination_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        file_stream.seek(0)
        with open(full_path, 'wb') as f:
            f.write(file_stream.read())
        return {"path": full_path, "provider": "local"}

    def get_file_stream(self, storage_path):
        full_path = self._safe_path(storage_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, 'rb') as f:
            return BytesIO(f.read())

    def generate_download_url(self, storage_path, expires_in):
        # Local provider doesn't generate pre-signed URLs in the same way S3 does.
        # Download is handled by the API itself.
        return f"/api/files/download?path={storage_path}"

    def delete_file(self, storage_path):
        full_path = self._safe_path(storage_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False

# Initialize the correct provider
if Config.STORAGE_PROVIDER == 'local':
    storage_provider = LocalStorageProvider(Config.UPLOAD_FOLDER)
else:
    # Future S3 implementation
    storage_provider = LocalStorageProvider(Config.UPLOAD_FOLDER)

class StorageService:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client.get_database()
        self.files_collection = self.db.get_collection("files")

    def validate_file(self, file_stream, allowed_types, max_size_bytes):
        # 1. Read first 2048 bytes for magic bytes validation
        header = file_stream.read(2048)
        file_stream.seek(0, 2) # seek to end
        size = file_stream.tell()
        file_stream.seek(0) # reset
        
        if size > max_size_bytes:
            raise ValueError(f"File exceeds maximum allowed size of {max_size_bytes} bytes")
            
        detected_mime = magic.from_buffer(header, mime=True)
        if detected_mime not in allowed_types:
            raise ValueError(f"Mime-type {detected_mime} is not allowed")
            
        return detected_mime, size

    def upload_file(self, file_stream, original_filename, uploaded_by, entity_type, entity_id=None):
        # Validation rules based on entity_type
        if entity_type == 'item_image':
            allowed_types = ['image/jpeg', 'image/png', 'image/webp']
            max_size = 5 * 1024 * 1024  # 5MB
        elif entity_type in ['invoice', 'payment_proof', 'attachment']:
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            max_size = 10 * 1024 * 1024 # 10MB
        else:
            raise ValueError("Unknown entity type for upload")
            
        mime_type, size_bytes = self.validate_file(file_stream, allowed_types, max_size)
        
        # Generate secure stored filename
        ext = os.path.splitext(original_filename)[1].lower()
        if not ext and mime_type == 'application/pdf': ext = '.pdf'
        elif not ext and mime_type == 'image/jpeg': ext = '.jpg'
        elif not ext and mime_type == 'image/png': ext = '.png'
        
        stored_filename = f"{uuid.uuid4()}{ext}"
        
        # Path format: entity_type/YYYY/MM/stored_filename
        now = datetime.utcnow()
        storage_path = f"{entity_type}s/{now.strftime('%Y/%m')}/{stored_filename}"
        
        # Save file using provider
        storage_result = storage_provider.save_file(file_stream, storage_path)
        
        # Create metadata document
        file_doc = {
            "filename": original_filename,
            "storedFilename": stored_filename,
            "mimeType": mime_type,
            "sizeBytes": size_bytes,
            "storageProvider": Config.STORAGE_PROVIDER,
            "storagePath": storage_path,
            "uploadedBy": ObjectId(uploaded_by) if uploaded_by else None,
            "linkedEntity": {
                "entityType": entity_type,
                "entityId": entity_id
            },
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = self.files_collection.insert_one(file_doc)
        
        return {
            "fileId": str(result.inserted_id),
            "filename": original_filename,
            "mimeType": mime_type,
            "sizeBytes": size_bytes
        }

    def get_file_metadata(self, file_id):
        return self.files_collection.find_one({"_id": ObjectId(file_id)})
        
    def get_file_stream(self, storage_path):
        return storage_provider.get_file_stream(storage_path)

storage_service = StorageService()
