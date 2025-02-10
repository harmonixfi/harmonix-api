#create PointResponse
import uuid
from pydantic import BaseModel
from typing import List, Dict, Any

class PointResponse(BaseModel):
    wallet: str
    amount: float
    points: float
    
