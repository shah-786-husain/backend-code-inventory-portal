import os
from dotenv import load_dotenv
from pymongo import MongoClient
from utils.password_helper import hash_password

load_dotenv()
MONGO_URI=os.getenv("MONGO_URI")
username = os.environ.get("MONGODB_USERNAME")
password = os.environ.get("MONGODB_PASS")
cluster_url = os.environ.get("CLUSTER_URL")
DB_NAME = os.environ.get("DB_NAME")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_NAME = os.environ.get("ADMIN_NAME")

if username and password and cluster_url:
    MONGO_URI = f"mongodb+srv://{username}:{password}@{cluster_url}/?retryWrites=true&w=majority&appName=Cluster1"
else:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/inventory_portal")
    DB_NAME = os.environ.get("DB_NAME","inventory_portal")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL","[EMAIL_ADDRESS]")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD","Admin@123")
ADMIN_NAME = os.environ.get("ADMIN_NAME","Admin")
if MONGO_URI == None:
    raise LookupError("Please set the MONGO_URI environment variable.")
if DB_NAME == None:
    raise LookupError("Please set the DB_NAME environment variable.")
if ADMIN_EMAIL == None:
    raise LookupError("Please set the ADMIN_EMAIL environment variable.")
if ADMIN_PASSWORD == None:
    raise LookupError("Please set the ADMIN_PASSWORD environment variable.")
if ADMIN_NAME == None:
    raise LookupError("Please set the ADMIN_NAME environment variable.")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_collection = db.users

existing_user = users_collection.find_one({"email": ADMIN_EMAIL})

if existing_user:
    print("Admin user already exists.")
else:
    admin_user = {
        "username": ADMIN_NAME,
        "name": ADMIN_NAME,
        "email": ADMIN_EMAIL.strip().lower(),
        "password": hash_password(ADMIN_PASSWORD),
        "role": "admin",
        "isActive": True
    }

    result = users_collection.insert_one(admin_user)
    print(f"Admin created successfully with id: {result.inserted_id}")