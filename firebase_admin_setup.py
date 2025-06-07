import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("/etc/secrets/serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()  # ✅ This is the correct Firestore client
