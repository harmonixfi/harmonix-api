from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserJoin(BaseModel):
    user_address: str
    referral_code: Optional[str] = None
    