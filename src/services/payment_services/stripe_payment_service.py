"""
Stripe payment service skeleton.

Contains helpers to manage plan catalog and team subscriptions.
Implementation will be filled after model review and migrations.
"""
from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any

from src.extensions import db
from src.models import PaymentPlan, PlanPrice, TeamSubscription, Team


class StripePaymentService:
    """Service for managing Stripe catalog and team subscriptions."""

    @staticmethod
    def get_active_plan_by_code(code: str) -> Optional[PaymentPlan]:
        return PaymentPlan.query.filter_by(code=code, is_active=True, is_deleted=False).first()

    @staticmethod
    def get_price_by_stripe_price_id(stripe_price_id: str) -> Optional[PlanPrice]:
        return PlanPrice.query.filter_by(stripe_price_id=stripe_price_id, is_active=True).first()

    @staticmethod
    def ensure_basic_plan_catalog() -> Dict[str, Any]:
        """
        Ensure a Basic plan and its monthly price exist in the local catalog.
        Commits the transaction to save the records.
        """
        plan = PaymentPlan.query.filter_by(code='basic', is_active=True, is_deleted=False).first()
        if not plan:
            plan = PaymentPlan(
                code='basic',
                display_name='Polaris Basic Plan',
                description='Basic plan with limited team members',
                stripe_product_id='prod_TJoXEaVfycYbGe',
                max_teams=1,
                max_projects=-1,
                max_team_members_per_team=2,
                max_project_members_per_project=-1,
                can_add_users_to_project=True,
                features={},
                is_active=True,
                is_deleted=False
            )
            db.session.add(plan)
            db.session.flush()  # Get the plan ID

        price = PlanPrice.query.filter_by(key='basic_monthly', is_active=True).first()
        if not price:
            price = PlanPrice(
                plan_id=plan.id,
                key='basic_monthly',
                nickname='Basic Monthly',
                currency='brl',
                amount_cents=0,  # base subscription amount; per-seat add-ons billed separately
                compare_at_cents=None,
                interval='month',
                interval_count=1,
                trial_days=14,
                stripe_price_id='price_1SNAuKAIZic08EhhdUtSPQ1r',
                per_seat_amount_cents=5000,  # 50 BRL per extra team member
                per_seat_metric='team_member',
                is_active=True
            )
            db.session.add(price)

        # Commit the transaction
        db.session.commit()
        
        return {'plan': plan, 'price': price}

    @staticmethod
    def compute_team_member_overage(team: Team, plan: PaymentPlan) -> int:
        """Return number of members over plan limit for the given team."""
        if plan.max_team_members_per_team < 0:
            return 0
        active_members = len([m for m in team.members if not m.is_deleted])
        return max(0, active_members - plan.max_team_members_per_team)



