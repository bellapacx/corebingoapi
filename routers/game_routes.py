from http.client import HTTPException
from fastapi import APIRouter, Header
from firebase_client import db
from utils.token import verify_token
from models.game import StartGameRequest
from uuid import uuid4
from firebase_admin import firestore  # ✅ Add this import
from models.winings import WiningEntry
from datetime import datetime
from isoweek import Week  # pip install isoweek

router = APIRouter()

@router.get("/games")
def get_games(authorization: str = Header(...)):
    verify_token(authorization.split(" ")[-1])
    return [doc.to_dict() for doc in db.collection("games").stream()]

@router.post("/games")
def create_game(data: dict, authorization: str = Header(...)):
    verify_token(authorization.split(" ")[-1])
    db.collection("games").add(data)
    return {"status": "game recorded"}



@router.post("/startgame")
async def start_game(data: StartGameRequest):
    round_id = str(uuid4())
    now = datetime.utcnow()
    week = Week.withdate(now.date())
    base_week_str = f"{week.year}-W{week.week}"  # e.g. "2025-W23"
    week_str = base_week_str  # This may be modified if payment_status == "paid"

    num_cards = len(data.selected_cards)
    total_bet = num_cards * data.bet_per_card
    commission_amount = total_bet * data.commission_rate
    
    # Fetch shop document by shop_id field
    shop_query = db.collection("shops").where("shop_id", "==", data.shop_id).limit(1).get()
    if not shop_query:
       raise HTTPException(status_code=404, detail="Shop not found")

    shop_doc = shop_query[0]
    shop_data = shop_doc.to_dict()
    billing_type = shop_data.get("billing_type", "prepaid")
    current_balance = shop_data.get("balance", 0.0)

    # Prepaid logic
    if billing_type == "prepaid":
       if current_balance < commission_amount:
        raise HTTPException(status_code=400, detail="Insufficient balance for prepaid shop")

    new_balance = current_balance - commission_amount
    db.collection("shops").document(shop_doc.id).update({
        "balance": new_balance
    })
    # Reference to weekly commission doc
    week_collection_ref = db.collection("shop_commissions").document(data.shop_id).collection("weekly_commissions")

    # Check if base week doc exists
    base_week_doc_ref = week_collection_ref.document(base_week_str)
    base_week_doc = base_week_doc_ref.get()

    if base_week_doc.exists:
        base_week_data = base_week_doc.to_dict()
        payment_status = base_week_data.get("payment_status", "unpaid")

        if payment_status == "paid":
            # Create a NEW weekly commission doc for this round
            # Generate a new unique week doc id by appending a timestamp or counter
            # Here we append current datetime as a simple unique suffix
            unique_suffix = now.strftime("%Y%m%d%H%M%S")
            week_str = f"{base_week_str}-{unique_suffix}"
            week_doc_ref = week_collection_ref.document(week_str)

            total_commission = commission_amount
            commissions = {round_id: commission_amount}
            total_payment = total_commission * 0.20
            payment_status_to_set = "unpaid"

        else:
            # Unpaid → update the existing doc, accumulate commission
            week_doc_ref = base_week_doc_ref

            total_commission = base_week_data.get("total_commission", 0) + commission_amount
            commissions = base_week_data.get("commissions", {})
            commissions[round_id] = commission_amount
            total_payment = total_commission * 0.20
            payment_status_to_set = "unpaid"
    else:
        # Week doc doesn't exist → create new
        week_doc_ref = base_week_doc_ref
        total_commission = commission_amount
        commissions = {round_id: commission_amount}
        total_payment = total_commission * 0.20
        payment_status_to_set = "unpaid"

    # Save the game round document
    game_data = {
        "round_id": round_id,
        "shop_id": data.shop_id,
        "selected_cards": data.selected_cards,
        "prize": data.prize,
        "interval": data.interval,
        "language": data.language,
        "bet_per_card": data.bet_per_card,
        "commission_rate": data.commission_rate,
        "commission_amount": commission_amount,
        "winning_pattern": data.winning_pattern,
        "status": "ongoing",
        "started_at": firestore.SERVER_TIMESTAMP,
        "date": now.strftime("%Y-%m-%d"),
    }
    db.collection("game_rounds").document(round_id).set(game_data)

    # Save or update the weekly commission document
    week_doc_ref.set({
        "shop_id": data.shop_id,
        "week": week_str,
        "total_commission": total_commission,
        "total_payment": total_payment,
        "payment_status": payment_status_to_set,
        "commissions": commissions,
    })

    return {
        "status": "success",
        "message": "Game started",
        "round_id": round_id,
        "commission_amount": commission_amount,
        "week": week_str,
        "total_commission": total_commission,
        "total_payment": total_payment
    }


@router.post("/winings")
async def record_wining(entry: WiningEntry):
    wining_id = str(uuid4())  # Unique ID for the document

    wining_data = {
        "card_id": entry.card_id,
        "round_id": entry.round_id,
        "shop_id": entry.shop_id,
        "prize": entry.prize,
        "timestamp": firestore.SERVER_TIMESTAMP,  # Requires import from google.cloud.firestore
    }

    db.collection("winings").document(wining_id).set(wining_data)

    return {"status": "success", "message": "Wining recorded", "id": wining_id}
