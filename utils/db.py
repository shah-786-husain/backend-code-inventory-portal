from pymongo import MongoClient
from config import Config

client = None
db_instance = None

class DatabaseProxy:
    def __getattr__(self, name):
        global db_instance
        if db_instance is None:
            db_instance = get_db()
        return getattr(db_instance, name)

    def __getitem__(self, name):
        global db_instance
        if db_instance is None:
            db_instance = get_db()
        return db_instance[name]

db = DatabaseProxy()

def init_db():
    global client, db_instance
    uri = Config.MONGO_URI
    client = MongoClient(uri)
    
    # Try to extract database name from URI, default to inventory_portal
    db_name = "inventory_portal"
    parsed_uri = uri.split("/")
    if len(parsed_uri) > 3:
        potential_db = parsed_uri[-1].split("?")[0]
        if potential_db:
            db_name = potential_db
            
    db_instance = client[db_name]
    
    # Create indexes for optimized search
    db_instance.users.create_index("username", unique=True)
    db_instance.users.create_index("email", unique=True)
    db_instance.items.create_index("itemCode", unique=True)
    db_instance.invoices.create_index("invoiceNumber", unique=True)

    # Dashboard-optimized indexes
    db_instance.items.create_index("status")
    db_instance.items.create_index("category")
    db_instance.items.create_index([("status", 1), ("availableQuantity", 1)])
    db_instance.items.create_index([("itemName", "text"), ("brand", "text"), ("model", "text")])
    db_instance.transactions.create_index([("timestamp", -1)])
    db_instance.transactions.create_index([("transactionType", 1), ("timestamp", -1)])
    db_instance.transactions.create_index("itemCode")

    # Asset requests and notifications indexes
    db_instance.asset_requests.create_index("requestId", unique=True)
    db_instance.asset_requests.create_index("requestedBy")
    db_instance.asset_requests.create_index("status")
    db_instance.asset_requests.create_index("createdAt")
    db_instance.notifications.create_index([("userId", 1), ("read", 1)])
    db_instance.notifications.create_index("recipientRole")
    db_instance.notifications.create_index("createdAt")

    # Generic Approval Engine indexes
    db_instance.approval_requests.create_index("approvalId", unique=True)
    db_instance.approval_requests.create_index("status")
    db_instance.approval_requests.create_index("targetType")
    db_instance.approval_requests.create_index("targetId")
    db_instance.approval_requests.create_index("requesterId")
    db_instance.approval_policies.create_index("policyCode", unique=True)

    # Warehouse / Location Management indexes
    db_instance.locations.create_index("locationCode", unique=True)
    db_instance.locations.create_index("status")
    db_instance.location_movements.create_index("itemCode")
    db_instance.location_movements.create_index("timestamp")

    # Maintenance / Repair / Asset Lifecycle indexes
    db_instance.maintenance_logs.create_index("maintenanceId", unique=True)
    db_instance.maintenance_logs.create_index("itemCode")
    db_instance.maintenance_logs.create_index("status")
    db_instance.maintenance_logs.create_index("scheduledDate")

    # Seed default warehouse locations
    try:
        from services.location_service import seed_default_locations
        seed_default_locations()
    except Exception as e:
        print(f"Error seeding locations on init: {e}")

    return db_instance

def get_db():
    global db_instance
    if db_instance is None:
        db_instance = init_db()
    return db_instance

