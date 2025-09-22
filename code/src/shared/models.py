from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

class Intent(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    amount: float
    duration: int
    purpose: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    signature: Optional[str] = None

class Offer(BaseModel):
    offer_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    bank_id: str
    interest_rate: float
    amount_approved: float
    repayment_period: int
    esg_summary: str
    carbon_adjusted_rate: float
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    signature: Optional[str] = None

class BankPolicy(BaseModel):
    bank_id: str
    max_loan_amount: float
    min_interest_rate: float
    max_interest_rate: float
    min_credit_score: int
    excluded_industries: list[str]
    esg_weight: float

class ConsumerPolicy(BaseModel):
    company_id: str
    min_esg_score: float
    max_interest_rate: float
    min_loan_amount: float
    carbon_impact_weight: float
    financial_terms_weight: float
    esg_weight: float