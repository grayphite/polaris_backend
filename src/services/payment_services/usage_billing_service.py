"""
Usage billing service: enforce plan limits, compute overage, and manage
subscription quantity alignment with Stripe (stubs only for now).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, UTC

import os
import stripe
from src.extensions import db
from src.models import Team, TeamSubscription, PaymentPlan, PlanPrice, TeamMember


@dataclass
class TeamMemberOverageInfo:
    current_active_members: int
    included_members_in_plan: int
    overage_member_count: int
    additional_member_cost_cents: int
    currency: str


class UsageBillingService:
    """Business logic for usage enforcement and per-seat overage billing."""

    @staticmethod
    def get_active_subscription(team_id: int) -> Optional[TeamSubscription]:
        return TeamSubscription.query.filter_by(team_id=team_id, is_active=True, is_deleted=False).first()

    @staticmethod
    def calculate_team_member_overage(team_id: int) -> Optional[TeamMemberOverageInfo]:
        team = Team.query.get(team_id)
        if not team:
            return None
        subscription = UsageBillingService.get_active_subscription(team_id)
        if not subscription or not subscription.plan or not subscription.price:
            return None

        plan: PaymentPlan = subscription.plan
        price: PlanPrice = subscription.price

        # Count all active members (including the team owner)
        active_members = len([m for m in team.members if not m.is_deleted])
        included = plan.max_team_members_per_team if plan.max_team_members_per_team >= 0 else active_members
        overage = max(0, active_members - included)

        additional_member_cost = price.per_seat_amount_cents or 0
        currency = price.currency or 'brl'

        return TeamMemberOverageInfo(
            current_active_members=active_members,
            included_members_in_plan=included,
            overage_member_count=overage,
            additional_member_cost_cents=additional_member_cost,
            currency=currency,
        )

    @staticmethod
    def calculate_current_overage_cost_cents(team_id: int) -> int:
        info = UsageBillingService.calculate_team_member_overage(team_id)
        if not info:
            return 0
        return info.overage_member_count * info.additional_member_cost_cents

    @staticmethod
    def validate_can_add_team_member(team_id: int) -> Dict[str, Any]:
        info = UsageBillingService.calculate_team_member_overage(team_id)
        if info is None:
            return {
                "allowed": False,
                "will_be_overage": False,
                "additional_member_cost_cents": 0,
                "currency": "brl",
                "current_active_members": 0,
                "included_members_in_plan": 0,
                "additional_members": 0,
                "reason": "Missing subscription or team"
            }
        
        # allowed: true if current members < plan limit, false if at or over limit
        allowed = info.current_active_members < info.included_members_in_plan
        
        # Calculate if adding one more member would exceed plan limits
        will_be_overage = info.current_active_members >= info.included_members_in_plan
        # Calculate how many members would be over limit after adding 1 more
        future_member_count = info.current_active_members + 1
        additional_members = max(0, future_member_count - info.included_members_in_plan)
        
        return {
            "allowed": allowed,
            "will_be_overage": will_be_overage,
            "current_active_members": info.current_active_members,
            "included_members_in_plan": info.included_members_in_plan,
            "additional_members": additional_members,
            "additional_member_cost_cents": info.additional_member_cost_cents if will_be_overage else 0,
            "currency": info.currency,
        }

    @staticmethod
    def sync_subscription_quantity_with_stripe(team_id: int) -> bool:
        """
        Align Stripe subscription items with membership counts using a two-item model:
        - Base item (plan price) remains quantity = 1
        - Overage item (overage price) quantity = max(0, active_members - included)
        Proration is enabled so changes affect the current period.
        Note: Team owner is included in the member count.
        """
        team = Team.query.get(team_id)
        subscription = UsageBillingService.get_active_subscription(team_id)
        if not team or not subscription or not subscription.stripe_subscription_id:
            return False

        # Ensure Stripe key is configured (routes set it normally; add fallback here)
        if not getattr(stripe, 'api_key', None):
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

        try:
            # Count all active members (including the team owner)
            active_members = len([m for m in team.members if not m.is_deleted])
            included = subscription.plan.max_team_members_per_team if subscription.plan.max_team_members_per_team >= 0 else 0
            overage_qty = max(0, active_members - included)

            # Retrieve subscription with items
            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id, expand=['items'])
            items = stripe_sub['items']['data'] if stripe_sub and stripe_sub.get('items') else []

            base_item = None
            overage_item = None
            overage_price_id = subscription.price.stripe_overage_price_id if subscription.price else None

            for it in items:
                if overage_price_id and it['price']['id'] == overage_price_id:
                    overage_item = it
                else:
                    # Assume first non-overage is the base plan item
                    if base_item is None:
                        base_item = it

            items_update = []

            # Ensure base item stays at quantity 1
            if base_item and base_item.get('quantity') != 1:
                items_update.append({'id': base_item['id'], 'quantity': 1})

            # Update or create overage item
            if overage_price_id:
                if overage_item:
                    if overage_item.get('quantity') != overage_qty:
                        items_update.append({'id': overage_item['id'], 'quantity': overage_qty})
                else:
                    if overage_qty > 0:
                        items_update.append({'price': overage_price_id, 'quantity': overage_qty})

            if not items_update:
                return False

            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                items=items_update,
                proration_behavior='create_prorations'
            )

            # Persist locally: keep quantity as active_members for reference
            subscription.quantity = max(1, active_members)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def add_team_member_with_billing_check(team_id: int, user_id: int, added_by: int) -> Dict[str, Any]:
        """
        Add a team member. If this addition exceeds included seats, caller should
        later trigger a Stripe quantity increase (proration). For now, we only
        return the intent and create the membership locally.
        """
        team = Team.query.get(team_id)
        if not team:
            return {"success": False, "error": "Team not found"}
        subscription = UsageBillingService.get_active_subscription(team_id)
        if not subscription:
            return {"success": False, "error": "No active subscription"}

        info = UsageBillingService.calculate_team_member_overage(team_id)
        if info is None:
            return {"success": False, "error": "Plan info unavailable"}

        # Create membership locally (no duplicate constraint handling here)
        member = TeamMember(team_id=team_id, user_id=user_id, role='member', added_by=added_by)
        db.session.add(member)
        db.session.flush()  # get member.id without commit

        will_be_overage = info.current_active_members >= info.included_members_in_plan
        billing_intent = None
        if will_be_overage:
            billing_intent = {
                "action": "increase_subscription_quantity",
                "new_quantity": (subscription.quantity or info.current_active_members) + 1,
                "proration": True,
                "additional_member_cost_cents": info.additional_member_cost_cents,
                "currency": info.currency,
            }

        return {"success": True, "member_id": member.id, "billing_intent": billing_intent}



