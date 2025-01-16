from pydantic import BaseModel


class UserAgreement(BaseModel):
    message: str
    signature: str
    wallet_address: str
