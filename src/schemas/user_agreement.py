import uuid
from pydantic import BaseModel


class BaseUserAgreement(BaseModel):
    message: str
    signature: str
    wallet_address: str


class UserAgreement(BaseUserAgreement):
    vault_id: uuid.UUID
