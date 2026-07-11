import os
from datetime import datetime, timedelta
from pymongo import MongoClient
from config import Config
from utils.password_helper import hash_password

def seed_database():
    uri = Config.MONGO_URI
    db_name = "inventory_portal"
    parsed_uri = uri.split("/")
    if len(parsed_uri) > 3:
        potential_db = parsed_uri[-1].split("?")[0]
        if potential_db:
            db_name = potential_db
            
    print(f"Connecting to MongoDB: {uri.split('@')[-1]} (Database: {db_name})")
    
    client = MongoClient(uri)
    db = client[db_name]
    
    # 1. Drop unused extra collections
    extra_cols = ['departments']
    for col in extra_cols:
        if col in db.list_collection_names():
            db.drop_collection(col)
            print(f"Dropped extra collection: {col}")
            
    # 2. Clear existing required collections to prevent duplicates
    required_cols = [
        'users', 'items', 'invoices', 'counters', 'transactions', 
        'assignments', 'returns', 'stock_adjustments', 'damage_reports', 
        'notifications', 'activity_logs', 'audit_logs', 'projects', 'devices', 
        'vendors', 'locations', 'roles', 'permissions', 'asset_requests',
        'maintenance_logs', 'approval_requests', 'approval_policies', 'location_movements',
        'warehouses'
    ]
    for col in required_cols:
        if col in db.list_collection_names():
            db.drop_collection(col)
            print(f"Cleared collection: {col}")
            
    # 3. Create indexes (same as db.py)
    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
    db.items.create_index("itemCode", unique=True)
    db.invoices.create_index("invoiceNumber", unique=True)
    
    # Seed default roles and permissions
    db.roles.insert_many([
        {
            "name": "admin",
            "displayName": "Administrator",
            "permissions": ["view_inventory", "manage_inventory", "log_transaction", "admin_reconciliation", "manage_invoices", "view_audit_logs", "manage_users"]
        },
        {
            "name": "store_head",
            "displayName": "Store Head",
            "permissions": ["view_inventory", "manage_inventory", "log_transaction", "manage_invoices", "view_audit_logs"]
        },
        {
            "name": "team_member",
            "displayName": "Team Member",
            "permissions": ["view_inventory"]
        },
        {
            "name": "viewer",
            "displayName": "Viewer",
            "permissions": ["view_inventory"]
        }
    ])
    db.permissions.insert_many([
        { "name": "view_inventory", "description": "Read-only access to item catalog" },
        { "name": "manage_inventory", "description": "Create, edit, and delete catalog items" },
        { "name": "log_transaction", "description": "Issue, return, consume, transfer, repair, or adjust stock" },
        { "name": "admin_reconciliation", "description": "Reconcile inventory audits and corrections" },
        { "name": "manage_invoices", "description": "Upload and modify vendor invoice documents" },
        { "name": "view_audit_logs", "description": "View system activity and audit logs" },
        { "name": "manage_users", "description": "Create, edit, and disable user credentials" }
    ])
    print("Seeded roles and permissions.")
    
    # 4. Seed Users
    hashed_pwd = hash_password("Admin@123")
    users_data = [
        {
            "username": "admin123",
            "name": "Admin User",
            "email": "admin123@gmail.com",
            "password": hashed_pwd,
            "role": "admin",
            "isActive": True,
            "department": "IT Operations",
            "phone": "+91 9999988888",
            "createdAt": datetime.utcnow()
        },
        {
            "username": "danish123",
            "name": "Danish Gaur",
            "email": "danish123@gmail.com",
            "password": hashed_pwd,
            "role": "store_head",
            "isActive": True,
            "department": "Hardware Store",
            "phone": "+91 8888877777",
            "createdAt": datetime.utcnow()
        },
        {
            "username": "owesh123",
            "name": "Owesh",
            "email": "owesh123@gmail.com",
            "password": hashed_pwd,
            "role": "team_member",
            "isActive": True,
            "department": "AI Research",
            "phone": "+91 7777766666",
            "createdAt": datetime.utcnow()
        },
        {
            "username": "test-analytics",
            "name": "Analytics Tester",
            "email": "test-analytics@irama.ai",
            "password": hashed_pwd,
            "role": "viewer",
            "isActive": True,
            "department": "Analytics Division",
            "phone": "+91 6666655555",
            "createdAt": datetime.utcnow()
        },
        {
            "username": "temmem",
            "name": "Team Member",
            "email": "temmem@gmail.com",
            "password": hashed_pwd,
            "role": "team_member",
            "isActive": True,
            "department": "Prototype Development",
            "phone": "+91 5555544444",
            "createdAt": datetime.utcnow()
        }
    ]
    users_result = db.users.insert_many(users_data)
    user_ids = {u["username"]: str(oid) for u, oid in zip(users_data, users_result.inserted_ids)}
    print(f"Seeded {len(users_data)} user registry accounts.")
    
    # 5. Seed Vendors
    vendors_data = [
        {
            "vendorCode": "VEN-0001",
            "vendorName": "Apex Ltd",
            "contactPerson": "Johan",
            "email": "johan123@gmail.com",
            "phone": "9877666658",
            "address": "Building No. 34, New Delhi",
            "gstNumber": "23GGGGGGTTTDD2",
            "notes": "Premium quality camera systems",
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        },
        {
            "vendorCode": "VEN-0002",
            "vendorName": "GKR Systems",
            "contactPerson": "Girish Kumar",
            "email": "gkr@gkr-systems.in",
            "phone": "9988776655",
            "address": "Electronic City, Bengaluru",
            "gstNumber": "29AABCG1234F1Z0",
            "notes": "Single board computers and custom enclosures",
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        },
        {
            "vendorCode": "VEN-0003",
            "vendorName": "iRAMA Technologies",
            "contactPerson": "Manager",
            "email": "procurement@irama.ai",
            "phone": "8888877777",
            "address": "Jayanagar, Bengaluru",
            "gstNumber": "29AAATI7890C1ZX",
            "notes": "Internal sourcing and device manufacturing",
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
    ]
    db.vendors.insert_many(vendors_data)
    print(f"Seeded {len(vendors_data)} vendors.")
    
    # 6. Seed Projects
    projects_data = [
        {"projectId": "PRJ-SAFETRIP", "projectName": "SAFETRIP Lab", "status": "Active", "description": "Lab safety alert automation using AI"},
        {"projectId": "PRJ-ROADSENSE", "projectName": "iRAMA RoadSense", "status": "Active", "description": "On-device traffic pattern monitoring"},
        {"projectId": "PRJ-FIELDSURVEY", "projectName": "Field Survey", "status": "Active", "description": "National highway traffic survey"},
        {"projectId": "PRJ-CLIENTDEMO", "projectName": "Client Demo", "status": "Active", "description": "Live demonstration kits"},
        {"projectId": "PRJ-PROTOTYPE", "projectName": "Prototype Development", "status": "Active", "description": "Early stage device hardware design"},
        {"projectId": "PRJ-MARKETREADY", "projectName": "Market-ready Devices", "status": "Active", "description": "Production units ready for shipment"}
    ]
    db.projects.insert_many(projects_data)
    print(f"Seeded {len(projects_data)} projects.")
    
    # 7. Seed Devices
    devices_data = [
        {"deviceId": "DEV-001", "deviceName": "iRAMA Edge Node V1", "projectCode": "PRJ-ROADSENSE", "status": "active"},
        {"deviceId": "DEV-002", "deviceName": "RoadSense Tracker GPS", "projectCode": "PRJ-ROADSENSE", "status": "active"},
        {"deviceId": "DEV-003", "deviceName": "SAFETRIP Camera Rig", "projectCode": "PRJ-SAFETRIP", "status": "active"}
    ]
    db.devices.insert_many(devices_data)
    print(f"Seeded {len(devices_data)} devices.")

    # 8. Seed Locations
    from services.location_service import seed_default_locations
    seed_default_locations()
    
    # 9. Seed Invoices
    invoices_data = [
        {
            "invoiceNumber": "INV-2026-001",
            "purchaseDate": "2026-06-01",
            "vendor": "GKR Systems",
            "totalAmount": 150000.0,
            "source": "Project alpha",
            "paymentStatus": "Paid",
            "invoiceFileUrl": "/api/files/mock-invoice-1",
            "paymentProofUrl": "/api/files/mock-proof-1",
            "linkedItemCodes": ["JET-ORN-001", "HUB-USB-001"],
            "uploadedBy": "admin123@gmail.com",
            "createdAt": datetime.utcnow()
        },
        {
            "invoiceNumber": "INV-2026-002",
            "purchaseDate": "2026-06-15",
            "vendor": "Apex Ltd",
            "totalAmount": 95000.0,
            "source": "SAFETRIP Lab",
            "paymentStatus": "Paid",
            "invoiceFileUrl": "/api/files/mock-invoice-2",
            "paymentProofUrl": "",
            "linkedItemCodes": ["CAM-USB-001"],
            "uploadedBy": "admin123@gmail.com",
            "createdAt": datetime.utcnow()
        }
    ]
    db.invoices.insert_many(invoices_data)
    print(f"Seeded {len(invoices_data)} invoices.")
    
    # 10. Seed Items
    items_data = [
        {
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "category": "Electronics",
            "subcategory": "Single Board Computers",
            "itemType": "Asset",
            "trackingMode": "Serialized",
            "quantity": 10,
            "availableQuantity": 7,
            "issuedQuantity": 3,
            "unit": "pcs",
            "brand": "Nvidia",
            "model": "Orin Nano 8GB Developer Kit",
            "vendor": "GKR Systems",
            "location": "WH1-ZA-R01-S01-B01",
            "locationArea": "WH1 - ZA",
            "storageUnit": "R01",
            "compartmentRow": "S01",
            "boxContainer": "B01",
            "ownership": "iRAMA RoadSense",
            "status": "Available",
            "unitPrice": 15000.0,
            "totalCost": 150000.0,
            "unitDetails": [
                {"unitCode": "JET-ORN-001-01", "serialNumber": "SN-JETORN-1001", "condition": "New", "status": "Issued"},
                {"unitCode": "JET-ORN-001-02", "serialNumber": "SN-JETORN-1002", "condition": "New", "status": "Issued"},
                {"unitCode": "JET-ORN-001-03", "serialNumber": "SN-JETORN-1003", "condition": "New", "status": "Issued"},
                {"unitCode": "JET-ORN-001-04", "serialNumber": "SN-JETORN-1004", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-05", "serialNumber": "SN-JETORN-1005", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-06", "serialNumber": "SN-JETORN-1006", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-07", "serialNumber": "SN-JETORN-1007", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-08", "serialNumber": "SN-JETORN-1008", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-09", "serialNumber": "SN-JETORN-1009", "condition": "New", "status": "In Store"},
                {"unitCode": "JET-ORN-001-10", "serialNumber": "SN-JETORN-1010", "condition": "New", "status": "In Store"}
            ],
            "createdAt": datetime.utcnow() - timedelta(days=30),
            "updatedAt": datetime.utcnow()
        },
        {
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "category": "Cameras",
            "subcategory": "USB Cameras",
            "itemType": "Tool",
            "trackingMode": "Serialized",
            "quantity": 5,
            "availableQuantity": 2,
            "issuedQuantity": 3,
            "unit": "pcs",
            "brand": "Mokose",
            "model": "C100 4K",
            "vendor": "Apex Ltd",
            "location": "WH1-ZC-R02-S01-B01",
            "locationArea": "WH1 - ZC",
            "storageUnit": "R02",
            "compartmentRow": "S01",
            "boxContainer": "B01",
            "ownership": "SAFETRIP Lab",
            "status": "Available",
            "unitPrice": 19000.0,
            "totalCost": 95000.0,
            "unitDetails": [
                {"unitCode": "CAM-USB-001-01", "serialNumber": "SN-MOKOSE-2001", "condition": "New", "status": "Issued"},
                {"unitCode": "CAM-USB-001-02", "serialNumber": "SN-MOKOSE-2002", "condition": "New", "status": "Issued"},
                {"unitCode": "CAM-USB-001-03", "serialNumber": "SN-MOKOSE-2003", "condition": "New", "status": "Issued"},
                {"unitCode": "CAM-USB-001-04", "serialNumber": "SN-MOKOSE-2004", "condition": "New", "status": "In Store"},
                {"unitCode": "CAM-USB-001-05", "serialNumber": "SN-MOKOSE-2005", "condition": "New", "status": "In Store"}
            ],
            "createdAt": datetime.utcnow() - timedelta(days=20),
            "updatedAt": datetime.utcnow()
        },
        {
            "itemCode": "PWR-PB-001",
            "itemName": "Mi Power Bank 20000mAh",
            "category": "Power Systems",
            "subcategory": "Power Banks",
            "itemType": "Consumable",
            "trackingMode": "Bulk",
            "quantity": 50,
            "availableQuantity": 34,
            "issuedQuantity": 16,
            "unit": "pcs",
            "brand": "Xiaomi",
            "model": "Mi Power Bank 3i",
            "vendor": "iRAMA Technologies",
            "location": "WH1-ZB-R01-S02-B02",
            "locationArea": "WH1 - ZB",
            "storageUnit": "R01",
            "compartmentRow": "S02",
            "boxContainer": "B02",
            "ownership": "Internal Team Usage",
            "status": "Available",
            "unitPrice": 1500.0,
            "totalCost": 75000.0,
            "unitDetails": [],
            "createdAt": datetime.utcnow() - timedelta(days=10),
            "updatedAt": datetime.utcnow()
        }
    ]
    db.items.insert_many(items_data)
    print(f"Seeded {len(items_data)} items catalog.")
    
    # 11. Seed Transactions, Assignments, Returns, Stock Adjustments, Damage Reports
    transactions_data = [
        {
            "transactionType": "issue",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-01"],
            "issuedTo": "owesh123@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Assigned for iRAMA RoadSense device prototyping",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=5)
        },
        {
            "transactionType": "issue",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "quantity": 1,
            "unitCodes": ["CAM-USB-001-01"],
            "issuedTo": "temmem@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Assigned for SAFETRIP Lab setup",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=15)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=2)
        },
        {
            "transactionType": "issue",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "quantity": 1,
            "unitCodes": ["CAM-USB-001-02"],
            "issuedTo": "temmem@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Secondary camera for SAFETRIP Lab prototyping",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=15)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=1)
        },
        {
            "transactionType": "issue",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-02"],
            "issuedTo": "temmem@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Jetson node for SAFETRIP Lab edge processing",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=20)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(hours=5)
        },
        {
            "transactionType": "issue",
            "itemCode": "PWR-PB-001",
            "itemName": "Mi Power Bank 20000mAh",
            "quantity": 1,
            "unitCodes": ["PWR-PB-001-01"],
            "issuedTo": "admin123@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Power bank for SAFETRIP Lab prototype rig",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=10)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=3)
        },
        {
            "transactionType": "issue",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "quantity": 1,
            "unitCodes": ["CAM-USB-001-03"],
            "issuedTo": "danish123@gmail.com",
            "actionBy": "danish123@gmail.com",
            "remarks": "Development camera unit for RoadSense calibration",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=12)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=4)
        },
        {
            "transactionType": "issue",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-03"],
            "issuedTo": "test-analytics@irama.ai",
            "actionBy": "danish123@gmail.com",
            "remarks": "Evaluation node for pattern analytics pipeline",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "expectedReturnDate": (datetime.utcnow() + timedelta(days=24)).isoformat(),
            "timestamp": datetime.utcnow() - timedelta(days=6)
        }
    ]
    db.transactions.insert_many(transactions_data)
    print(f"Seeded {len(transactions_data)} transactions.")
    
    # Seed assignments (Items currently checked out by users)
    assignments_data = [
        {
            "username": "owesh123",
            "email": "owesh123@gmail.com",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "category": "Electronics",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-01"],
            "location": "WH1-ZA-R01-S01-B01",
            "brand": "Nvidia",
            "model": "Orin Nano 8GB Developer Kit",
            "status": "Issued",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(days=5),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=25)
        },
        {
            "username": "temmem",
            "email": "temmem@gmail.com",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "category": "Cameras",
            "quantity": 2,
            "unitCodes": ["CAM-USB-001-01", "CAM-USB-001-02"],
            "location": "WH1-ZC-R02-S01-B01",
            "brand": "Mokose",
            "model": "C100 4K",
            "status": "Issued",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(days=2),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=13)
        },
        {
            "username": "temmem",
            "email": "temmem@gmail.com",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "category": "Electronics",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-02"],
            "location": "WH1-ZA-R01-S01-B01",
            "brand": "Nvidia",
            "model": "Orin Nano 8GB Developer Kit",
            "status": "Issued",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(hours=5),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=20)
        },
        {
            "username": "admin123",
            "email": "admin123@gmail.com",
            "itemCode": "PWR-PB-001",
            "itemName": "Mi Power Bank 20000mAh",
            "category": "Power Systems",
            "quantity": 1,
            "unitCodes": ["PWR-PB-001-01"],
            "location": "WH1-ZB-R01-S02-B02",
            "brand": "Xiaomi",
            "model": "Mi Power Bank 3i",
            "status": "Issued",
            "projectId": "PRJ-SAFETRIP",
            "deviceId": "DEV-003",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(days=3),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=10)
        },
        {
            "username": "danish123",
            "email": "danish123@gmail.com",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "category": "Cameras",
            "quantity": 1,
            "unitCodes": ["CAM-USB-001-03"],
            "location": "WH1-ZC-R02-S01-B01",
            "brand": "Mokose",
            "model": "C100 4K",
            "status": "Issued",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(days=4),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=12)
        },
        {
            "username": "test-analytics",
            "email": "test-analytics@irama.ai",
            "itemCode": "JET-ORN-001",
            "itemName": "Nvidia Jetson Orin Nano 8GB",
            "category": "Electronics",
            "quantity": 1,
            "unitCodes": ["JET-ORN-001-03"],
            "location": "WH1-ZA-R01-S01-B01",
            "brand": "Nvidia",
            "model": "Orin Nano 8GB Developer Kit",
            "status": "Issued",
            "projectId": "PRJ-ROADSENSE",
            "deviceId": "DEV-001",
            "assignedBy": "danish123@gmail.com",
            "assignedAt": datetime.utcnow() - timedelta(days=6),
            "expectedReturnDate": datetime.utcnow() + timedelta(days=24)
        }
    ]
    db.assignments.insert_many(assignments_data)
    print(f"Seeded {len(assignments_data)} active assignments.")
    
    # Seed returns
    returns_data = [
        {
            "itemCode": "PWR-PB-001",
            "itemName": "Mi Power Bank 20000mAh",
            "returnedBy": "owesh123@gmail.com",
            "quantity": 2,
            "condition": "Good",
            "receivedBy": "danish123@gmail.com",
            "remarks": "Returned after road trial",
            "timestamp": datetime.utcnow() - timedelta(days=10)
        }
    ]
    db.returns.insert_many(returns_data)
    print(f"Seeded {len(returns_data)} return records.")
    
    # Seed stock adjustments
    stock_adjustments_data = [
        {
            "itemCode": "PWR-PB-001",
            "itemName": "Mi Power Bank 20000mAh",
            "adjustmentType": "Cycle Count",
            "quantityDifference": 5,
            "adjustedBy": "admin123@gmail.com",
            "remarks": "Reconciliation after audit",
            "timestamp": datetime.utcnow() - timedelta(days=15)
        }
    ]
    db.stock_adjustments.insert_many(stock_adjustments_data)
    print(f"Seeded {len(stock_adjustments_data)} stock adjustments.")
    
    # Seed damage reports
    damage_reports_data = [
        {
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "unitCode": "CAM-USB-001-05",
            "reportedBy": "owesh123@gmail.com",
            "damageSeverity": "Medium",
            "remarks": "Lens scratch noticed after lab deployment",
            "status": "Under Review",
            "timestamp": datetime.utcnow() - timedelta(days=3)
        }
    ]
    db.damage_reports.insert_many(damage_reports_data)
    print(f"Seeded {len(damage_reports_data)} damage reports.")
    
    # 12. Seed Counters
    counters_data = [
        {"_id": "item_code_JET-ORN", "seq": 1},
        {"_id": "item_code_CAM-USB", "seq": 1},
        {"_id": "item_code_GPS-USB", "seq": 1},
        {"_id": "item_code_PWR-PB", "seq": 1},
        {"_id": "invoice_record_id", "seq": 2}
    ]
    db.counters.insert_many(counters_data)
    print("Seeded database counters.")
    
    # 13. Seed Activity Logs / Audit Logs
    audit_logs_data = [
        {
            "action": "item_created",
            "details": "Item 'Nvidia Jetson Orin Nano 8GB' (JET-ORN-001) created with initial quantity 10",
            "entityType": "item",
            "entityId": "JET-ORN-001",
            "oldValue": None,
            "newValue": {"itemCode": "JET-ORN-001", "quantity": 10, "status": "Available"},
            "performedBy": users_result.inserted_ids[0], # admin
            "performedByUsername": "admin123@gmail.com",
            "ipAddress": "127.0.0.1",
            "timestamp": datetime.utcnow() - timedelta(days=30)
        },
        {
            "action": "item_created",
            "details": "Item 'Mokose 4K USB Camera' (CAM-USB-001) created with initial quantity 5",
            "entityType": "item",
            "entityId": "CAM-USB-001",
            "oldValue": None,
            "newValue": {"itemCode": "CAM-USB-001", "quantity": 5, "status": "Available"},
            "performedBy": users_result.inserted_ids[0],
            "performedByUsername": "admin123@gmail.com",
            "ipAddress": "127.0.0.1",
            "timestamp": datetime.utcnow() - timedelta(days=20)
        },
        {
            "action": "user_created",
            "details": "Created user account 'temmem' with role 'team_member'",
            "entityType": "user",
            "entityId": str(users_result.inserted_ids[4]),
            "oldValue": None,
            "newValue": {"username": "temmem", "role": "team_member"},
            "performedBy": users_result.inserted_ids[0],
            "performedByUsername": "admin123@gmail.com",
            "ipAddress": "127.0.0.1",
            "timestamp": datetime.utcnow() - timedelta(days=10)
        }
    ]
    db.audit_logs.insert_many(audit_logs_data)
    # Also write duplicate to activity_logs
    db.activity_logs.insert_many(audit_logs_data)
    print("Seeded audit logs and activity logs.")
    
    # 14. Seed Asset Requests
    asset_requests_data = [
        {
            "requestId": "REQ-202607-0001",
            "requestCode": "REQ-202607-0001",
            "employeeName": "Owesh",
            "departmentId": "AI Research",
            "priority": "high",
            "status": "pending",
            "items": [
                {
                    "itemName": "Nvidia Jetson Orin Nano 8GB",
                    "quantity": 1,
                    "unit": "pcs",
                    "purpose": "RoadSense Edge node training"
                }
            ],
            "remarks": "Urgent requirement for upcoming sprint demo",
            "requestedBy": user_ids["owesh123"],
            "requestedByUsername": "owesh123@gmail.com",
            "createdAt": datetime.utcnow() - timedelta(days=2),
            "updatedAt": datetime.utcnow() - timedelta(days=2)
        },
        {
            "requestId": "REQ-202607-0002",
            "requestCode": "REQ-202607-0002",
            "employeeName": "Team Member",
            "departmentId": "Prototype Development",
            "priority": "medium",
            "status": "approved",
            "items": [
                {
                    "itemName": "Mokose 4K USB Camera",
                    "quantity": 2,
                    "unit": "pcs",
                    "purpose": "SAFETRIP Camera Rig setup"
                }
            ],
            "remarks": "Dual cameras needed for stereoscopic view experiments",
            "requestedBy": user_ids["temmem"],
            "requestedByUsername": "temmem@gmail.com",
            "approvedBy": "danish123@gmail.com",
            "createdAt": datetime.utcnow() - timedelta(days=3),
            "updatedAt": datetime.utcnow() - timedelta(days=2)
        }
    ]
    req_result = db.asset_requests.insert_many(asset_requests_data)
    req_ids = [str(oid) for oid in req_result.inserted_ids]
    print("Seeded asset requests.")
    
    # 15. Seed Approval Policies and Requests
    from services.approval_policy_service import seed_default_policies
    from bson import ObjectId
    seed_default_policies()
    print("Seeded default approval policies.")
    
    approval_requests_data = [
        {
            "approvalId": "APR-202607-0001",
            "targetType": "asset_request",
            "targetId": ObjectId(req_ids[0]),
            "requesterId": ObjectId(user_ids["owesh123"]),
            "requesterUsername": "owesh123@gmail.com",
            "status": "pending",
            "currentStepIndex": 0,
            "steps": [
                {
                    "stepIndex": 0,
                    "stepName": "Manager Review",
                    "requiredRoles": ["manager"],
                    "status": "pending",
                    "reviewedBy": None,
                    "reviewedByUsername": None,
                    "reviewedAt": None,
                    "comments": ""
                },
                {
                    "stepIndex": 1,
                    "stepName": "Store Head Allocation",
                    "requiredRoles": ["store_head", "admin"],
                    "status": "pending",
                    "reviewedBy": None,
                    "reviewedByUsername": None,
                    "reviewedAt": None,
                    "comments": ""
                }
            ],
            "summarySnapshot": {
                "requester": "Owesh",
                "department": "AI Research",
                "items": "1x Nvidia Jetson Orin Nano 8GB"
            },
            "history": [
                {
                    "action": "submitted",
                    "stepIndex": None,
                    "operatorId": ObjectId(user_ids["owesh123"]),
                    "operatorUsername": "owesh123@gmail.com",
                    "comments": "Initiated approval request",
                    "timestamp": datetime.utcnow() - timedelta(days=2)
                }
            ],
            "createdAt": datetime.utcnow() - timedelta(days=2),
            "updatedAt": datetime.utcnow() - timedelta(days=2)
        }
    ]
    db.approval_requests.insert_many(approval_requests_data)
    print("Seeded approval requests.")
    
    # 16. Seed Location Movements
    location_movements_data = [
        {
            "movementId": "MOV-202607-0001",
            "itemId": ObjectId(db.items.find_one({"itemCode": "JET-ORN-001"})["_id"]),
            "itemCode": "JET-ORN-001",
            "serialNumber": "SN-JETORN-1003",
            "quantity": 1,
            "sourceLocationCode": "WH1-ZA-R01-S01-B01",
            "destinationLocationCode": "WH1-ZA-R01-S01-B02",
            "reason": "Rack Reorganization",
            "performedBy": "danish123@gmail.com",
            "timestamp": datetime.utcnow() - timedelta(days=4),
            "remarks": "Moved via warehouse management tool. Operator: danish123@gmail.com"
        }
    ]
    db.location_movements.insert_many(location_movements_data)
    print("Seeded location movements.")
    
    # 17. Seed Maintenance Logs
    db.drop_collection("maintenance_logs")
    maintenance_logs_data = [
        {
            "maintenanceId": "MNT-202607-0001",
            "itemCode": "CAM-USB-001",
            "itemName": "Mokose 4K USB Camera",
            "serialNumber": "SN-MOKOSE-2003",
            "maintenanceType": "repair",
            "status": "active",
            "title": "Lens Focus Recalibration",
            "details": "Autofocus mechanism sticking on zoom operations.",
            "vendor": "Apex Ltd",
            "cost": 2500.0,
            "warrantyCovered": True,
            "scheduledDate": (datetime.utcnow() + timedelta(days=5)).isoformat(),
            "createdAt": datetime.utcnow() - timedelta(days=1),
            "performedBy": "danish123@gmail.com"
        }
    ]
    db.maintenance_logs.insert_many(maintenance_logs_data)
    print("Seeded maintenance logs.")
    
    # 18. Seed Notifications
    notifications_data = [
        {
            "userId": str(users_result.inserted_ids[4]), # temmem
            "message": "You have been assigned 1 Nvidia Jetson Orin Nano 8GB (JET-ORN-001-02) for the SAFETRIP Lab project.",
            "read": False,
            "type": "assignment",
            "link": "/my-items",
            "createdAt": datetime.utcnow() - timedelta(hours=5)
        },
        {
            "userId": str(users_result.inserted_ids[4]), # temmem
            "message": "You have been assigned 2 Mokose 4K USB Cameras (CAM-USB-001-01, CAM-USB-001-02).",
            "read": False,
            "type": "assignment",
            "link": "/my-items",
            "createdAt": datetime.utcnow() - timedelta(days=1)
        }
    ]
    db.notifications.insert_many(notifications_data)
    print("Seeded user notifications.")

    print("\nDatabase seeding completed successfully!")

if __name__ == '__main__':
    seed_database()
