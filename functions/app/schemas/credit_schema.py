from pydantic import BaseModel


class CreditSummaryResponse(BaseModel):
    """What the signed-in user can spend right now. Free credits are a one-time
    signup bonus and never renew; questions reset at midnight IST."""
    free_left: int
    free_monthly: int
    purchased_balance: int
    available: int
    questions_left: int
    is_paid: bool
    short_credit_cost: int


class PlanLimitsResponse(BaseModel):
    """Public allowances and prices shown in the app's copy."""
    user_monthly_credits: int
    user_daily_questions: int
    short_credit_cost: int
    free_retention_hours: int
    paid_retention_hours: int
