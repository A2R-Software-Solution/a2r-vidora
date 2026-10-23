from pydantic import BaseModel


class CreditSummaryResponse(BaseModel):
    """What the requester can spend right now. Free allowances reset at midnight IST."""
    free_left: int
    free_daily: int
    purchased_balance: int
    available: int
    questions_left: int
    is_paid: bool
    short_credit_cost: int
