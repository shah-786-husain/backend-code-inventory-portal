import os
import sys
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

class Config:
    ENV = os.getenv("FLASK_ENV", "development").lower()
    _mongo_username = os.getenv("MONGODB_USERNAME")
    _mongo_pass = os.getenv("MONGODB_PASS")
    _cluster_url = os.getenv("CLUSTER_URL")
    _db_name = os.getenv("DB_NAME", "inventory_portal")
    if _mongo_username and _mongo_pass and _cluster_url:
        _clean_cluster = _cluster_url.lstrip("@")
        MONGO_URI = f"mongodb+srv://{_mongo_username}:{_mongo_pass}@{_clean_cluster}/{_db_name}?retryWrites=true&w=majority"
    else:
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/inventory_portal")
    JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-inventory-key-change-in-prod")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", 24))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"))
    STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")
    STORAGE_BUCKET_NAME = os.getenv("STORAGE_BUCKET_NAME", "irama-inventory-assets")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true" if ENV != "production" else False

    # Strict production validation checks
    if ENV == "production":
        if JWT_SECRET == "super-secret-inventory-key-change-in-prod":
            print("FATAL SECURITY EXCEPTION: Default JWT_SECRET must be replaced in production environment!", file=sys.stderr)
            raise ValueError("JWT_SECRET must be configured securely in production mode.")
        if "localhost" in MONGO_URI or "127.0.0.1" in MONGO_URI:
            print("WARNING: Production environment is using a local loopback MongoDB connection.", file=sys.stderr)
