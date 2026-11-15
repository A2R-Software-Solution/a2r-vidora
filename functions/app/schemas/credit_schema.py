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


class PlanLimitsResponse(BaseModel):
    """Public allowances and prices shown in the app's copy."""
    guest_daily_credits: int
    user_daily_credits: int
    guest_daily_questions: int
    user_daily_questions: int
    short_credit_cost: int
    free_retention_hours: int
    paid_retention_hours: int
