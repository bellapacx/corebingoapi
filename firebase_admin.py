import firebase_admin
from firebase_admin import credentials, firestore

print(">>> firebase_admin_setup.py loaded")  # Optional debug

cred = credentials.Certificate("/etc/secrets/serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()
