from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from firebase_admin_setup import db
from models.shop import Shop
from utils.token import create_access_token, verify_token
from passlib.context import CryptContext

from firebase_admin import firestore  # Ensure you have firebase_admin installed

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class LoginRequest(BaseModel):
    shopId: str
    username: str
    password: str

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str):
    return pwd_context.hash(password)

@router.post("/loginshop")
def login(data: LoginRequest):
    users_ref = db.collection("shops")
    query = users_ref.where("shop_id", "==", data.shopId).where("username", "==", data.username).limit(1)
    docs = list(query.stream())

    if not docs:
        raise HTTPException(status_code=401, detail="Invalid shop ID or username")

    user_data = docs[0].to_dict()

    hashed_password = user_data.get("password")
    if not hashed_password or not verify_password(data.password, hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Create JWT token with user info payload
    token_data = {
        "sub": user_data.get("username"),
        "shop_id": user_data.get("shop_id"),
        "role": "Shop Operator"
    }
    token = create_access_token(token_data)

    return {
        "token": token,
        "user": {
            "name": user_data.get("username"),
            "role": "Shop Operator",
            "shopId": user_data.get("shop_id"),
            "permissions": ["game_control", "card_management", "reports"],
            "balance": user_data.get("balance", 0)
        }
    }

@router.get("/shops")
def get_shops(authorization: str = Header(...)):
    verify_token(authorization.split(" ")[-1])
    return [doc.to_dict() for doc in db.collection("shops").stream()]

@router.post("/shops")
def create_shop(shop: Shop, authorization: str = Header(...)):
    verify_token(authorization.split(" ")[-1])

    # Hash the password before saving
    shop_data = shop.dict()
    shop_data['password'] = hash_password(shop_data['password'])

    db.collection("shops").add(shop_data)
    return {"status": "created"}

@router.get("/balance/{shop_id}")
async def get_shop_balance(shop_id: str):
    docs = db.collection("shops").stream()
    
    for doc in docs:
        data = doc.to_dict()
        if data.get("shop_id") == shop_id:
            balance = data.get("balance", 0)
            return {"balance": balance}
    
    raise HTTPException(status_code=404, detail="Shop not found")




@router.get("/shop_commissions/{shop_id}")
async def get_shop_weekly_commissions(shop_id: str):
    commissions_ref = db.collection("shop_commissions").document(shop_id).collection("weekly_commissions")
    docs = commissions_ref.stream()

    result = []
    for doc in docs:
        data = doc.to_dict()
        data["week_id"] = doc.id
        result.append(data)

    return {
        "shop_id": shop_id,
        "weekly_commissions": result
    }

@router.post("/shop_commissions/{shop_id}/pay/{week_id}")
async def mark_commission_paid(shop_id: str, week_id: str):
    week_doc_ref = db.collection("shop_commissions").document(shop_id).collection("weekly_commissions").document(week_id)
    week_doc = week_doc_ref.get()

    if not week_doc.exists:
        raise HTTPException(status_code=404, detail="Week commission not found")

    week_doc_ref.update({
        "payment_status": "paid",
        "paid_at": firestore.SERVER_TIMESTAMP
    })

    return {
        "status": "success",
        "message": f"Week {week_id} marked as paid"
    }

@router.get("/report/{shop_id}")
def get_shop_games(shop_id: str):
    try:
        games_query = db.collection("game_rounds").where("shop_id", "==", shop_id)
        games_docs = games_query.stream()

        games = []
        for doc in games_docs:
            data = doc.to_dict()
            data["round_id"] = doc.id
            games.append(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch games: {e}")

    if not games:
        return {"shop_id": shop_id, "games": [], "message": "No games found"}

    return {"shop_id": shop_id, "games": games}
