from datetime import datetime
import uuid
from pydantic import BaseModel


class PricePerShareHistoryResponse(BaseModel):
    id: uuid.UUID
    vault_id: uuid.UUID
    price_per_share: float
    datetime: datetime
