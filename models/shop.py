from pydantic import BaseModel

class Shop(BaseModel):
    shop_id: str
    username: str
    password: str
    balance: float