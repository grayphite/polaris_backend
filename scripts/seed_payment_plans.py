"""
Seed/ensure payment plan catalog and set Stripe price IDs.

Usage examples:
  # Set overage price id only
  python dev_scripts/seed_payment_plans.py --overage-price-id price_1SOEJO...

  # Set base monthly price id as well
  python dev_scripts/seed_payment_plans.py --base-price-id price_1SNAuK...

Notes:
  - Runs inside the Flask app context
  - Ensures the Basic plan and price exist (idempotent)
  - Updates PlanPrice.stripe_overage_price_id and/or PlanPrice.stripe_price_id if provided
  - Safe for production: only touches provided fields
"""
import argparse
import sys
import os
from typing import Optional

# Ensure project root is on sys.path so `src` can be imported when running directly
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.main import create_app
from src.extensions import db
from src.services.payment_services.stripe_payment_service import StripePaymentService
from src.models import PlanPrice


def ensure_basic_and_set_prices(overage_price_id: Optional[str], base_price_id: Optional[str]) -> None:
    result = StripePaymentService.ensure_basic_plan_catalog()
    price: PlanPrice = result['price']

    changed = False
    if overage_price_id:
        if getattr(price, 'stripe_overage_price_id', None) != overage_price_id:
            price.stripe_overage_price_id = overage_price_id
            changed = True
    if base_price_id:
        if getattr(price, 'stripe_price_id', None) != base_price_id:
            price.stripe_price_id = base_price_id
            changed = True

    if changed:
        db.session.commit()

    print({
        'plan_id': result['plan'].id,
        'plan_code': result['plan'].code,
        'price_id': price.id,
        'price_key': price.key,
        'stripe_price_id': price.stripe_price_id,
        'stripe_overage_price_id': getattr(price, 'stripe_overage_price_id', None),
        'updated': changed,
    })


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='Seed payment plans and set Stripe price ids')
    parser.add_argument('--overage-price-id', dest='overage_price_id', default=None,
                        help='Stripe price id for overage (e.g., 50 BRL per extra member)')
    parser.add_argument('--base-price-id', dest='base_price_id', default=None,
                        help='Stripe price id for the base recurring price (e.g., 500 BRL monthly)')
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        ensure_basic_and_set_prices(args.overage_price_id, args.base_price_id)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

"""
Seed or update payment plans and prices from an inline config.

Edit the PLANS_CONFIG list below and run this script after applying migrations.

Usage (from repo root):
  python -m dev_scripts.seed_payment_plans
"""
import os
from typing import List, Dict, Any

from dotenv import load_dotenv

from src.main import create_app
from src.extensions import db
from src.models import PaymentPlan, PlanPrice, TeamSubscription, Team, User


# ---------------------------------------------------------------------------
# Edit this configuration to add/update plans and prices
# - Use -1 for unlimited counts
# - Keys `code` (plan) and `key` (price) should be unique and stable
# - Stripe IDs are optional here; add them when available
# ---------------------------------------------------------------------------
PLANS_CONFIG: List[Dict[str, Any]] = [
    {
        "plan": {
            "code": "basic",
            "display_name": "Premium Plan",
            "description": "Premium plan with limited team members",
            "stripe_product_id": "prod_TJoXEaVfycYbGe",
            "max_teams": 1,
            "max_projects": -1,
            "max_team_members_per_team": 2,
            "max_project_members_per_project": -1,
            "can_add_users_to_project": True,
            "features": {},
            "is_active": True,
            "sort_order": 100,
        },
        "prices": [
            {
                "key": "basic_monthly",
                "nickname": "Premium Monthly",
                "currency": "brl",
                "amount_cents": 0,  # base monthly price in cents
                "compare_at_cents": None,
                "interval": "month",
                "interval_count": 1,
                "trial_days": 14,
                "stripe_price_id": "price_1SNAuKAIZic08EhhdUtSPQ1r",
                "per_seat_amount_cents": 5000,  # 50 BRL per extra team member
                "per_seat_metric": "team_member",
                "is_active": True,
            }
        ],
    }
]


def upsert_plan(plan_data: Dict[str, Any]) -> PaymentPlan:
    code = plan_data["code"].strip()
    plan = PaymentPlan.query.filter_by(code=code).first()
    if not plan:
        plan = PaymentPlan(code=code)
        db.session.add(plan)

    # Assign fields if provided
    for field in [
        "display_name",
        "description",
        "stripe_product_id",
        "max_teams",
        "max_projects",
        "max_team_members_per_team",
        "max_project_members_per_project",
        "can_add_users_to_project",
        "features",
        "is_active",
        "sort_order",
    ]:
        if field in plan_data:
            setattr(plan, field, plan_data[field])

    return plan


def upsert_price(plan: PaymentPlan, price_data: Dict[str, Any]) -> PlanPrice:
    key = price_data["key"].strip()
    price = PlanPrice.query.filter_by(key=key).first()
    if not price and price_data.get("stripe_price_id"):
        price = PlanPrice.query.filter_by(stripe_price_id=price_data["stripe_price_id"]).first() or price
    if not price:
        price = PlanPrice(plan=plan, key=key)
        db.session.add(price)

    # Assign fields if provided
    for field in [
        "nickname",
        "currency",
        "amount_cents",
        "compare_at_cents",
        "interval",
        "interval_count",
        "trial_days",
        "stripe_price_id",
        "per_seat_amount_cents",
        "per_seat_metric",
        "is_active",
    ]:
        if field in price_data:
            setattr(price, field, price_data[field])

    # Ensure association to the plan
    price.plan = plan
    return price


def create_sample_subscription(team_id: int, billing_user_id: int, plan_code: str = "basic") -> TeamSubscription:
    """Create a sample subscription for testing purposes."""
    plan = PaymentPlan.query.filter_by(code=plan_code).first()
    if not plan:
        print(f"Plan '{plan_code}' not found. Please seed plans first.")
        return None
    
    price = PlanPrice.query.filter_by(plan_id=plan.id, is_active=True).first()
    if not price:
        print(f"No active price found for plan '{plan_code}'.")
        return None
    
    # Check if subscription already exists
    existing = TeamSubscription.query.filter_by(team_id=team_id, is_deleted=False).first()
    if existing:
        print(f"Team {team_id} already has an active subscription.")
        return existing
    
    subscription = TeamSubscription(
        team_id=team_id,
        billing_user_id=billing_user_id,
        plan_id=plan.id,
        price_id=price.id,
        status='trialing',
        trial_end=None,  # Will be set when Stripe webhook comes in
        quantity=1
    )
    
    db.session.add(subscription)
    return subscription


def main():
    load_dotenv("./.env")
    app = create_app()
    with app.app_context():
        print("Seeding payment plans and prices...")
        for entry in PLANS_CONFIG:
            plan = upsert_plan(entry["plan"])  # plan row
            for price_entry in entry.get("prices", []):
                upsert_price(plan, price_entry)
        
        db.session.commit()
        print("Plans and prices upserted successfully.")

if __name__ == "__main__":
    main()
