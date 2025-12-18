"""
Update payment plans with LIVE Stripe product and price IDs.

This script UPDATES ONLY existing records with LIVE mode Stripe IDs.
It will NOT create new records - if records don't exist, it does nothing.

Usage (from repo root):
    python scripts/seed_payment_plans_live.py

What it does:
    1. Checks if Basic plan exists - if not, aborts (no changes)
    2. Updates the plan with LIVE Stripe product ID
    3. Checks if basic_monthly price exists - if not, aborts (no changes)
    4. Updates the price with LIVE Stripe price IDs (base + overage)

This is an ATOMIC operation - either all updates succeed or nothing changes.

LIVE Stripe IDs (configured in this script):
    - Product ID: prod_TRMCWQkurpm5nb
    - Base Price ID: price_1SUTUUPP3GthwlsKIiacVIoi
    - Overage Price ID: price_1SUTb7PP3GthwlsKncRidi0Q

⚠️  WARNING: This script will UPDATE your database with LIVE Stripe IDs.
    Make sure you have a database backup before running.
"""
import sys
import os
from typing import Optional

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from src.main import create_app
from src.extensions import db
from src.models import PaymentPlan, PlanPrice

# Load environment variables
load_dotenv()

# ============================================================================
# LIVE STRIPE IDs - Update these if your live IDs change
# ============================================================================
LIVE_STRIPE_PRODUCT_ID = "prod_TRMCWQkurpm5nb"
LIVE_STRIPE_PRICE_ID = "price_1SUTUUPP3GthwlsKIiacVIoi"
LIVE_STRIPE_OVERAGE_PRICE_ID = "price_1SUTb7PP3GthwlsKncRidi0Q"

# Plan configuration (same as test mode, but with live Stripe IDs)
PLAN_CODE = "basic"
PLAN_DISPLAY_NAME = "Premium Plan"
PLAN_DESCRIPTION = "Premium plan with limited team members"

# Price configuration
PRICE_KEY = "basic_monthly"
PRICE_NICKNAME = "Premium Monthly"
CURRENCY = "brl"
AMOUNT_CENTS = 0  # Base subscription amount (per-seat add-ons billed separately)
INTERVAL = "month"
INTERVAL_COUNT = 1
TRIAL_DAYS = 7
PER_SEAT_AMOUNT_CENTS = 5000  # 50 BRL per extra team member
PER_SEAT_METRIC = "team_member"

# Plan limits
MAX_TEAMS = 1
MAX_PROJECTS = -1  # -1 = unlimited
MAX_TEAM_MEMBERS_PER_TEAM = 2
MAX_PROJECT_MEMBERS_PER_PROJECT = -1  # -1 = unlimited
CAN_ADD_USERS_TO_PROJECT = True


def update_basic_plan_with_live_ids() -> dict:
    """
    Update existing Basic plan and price with LIVE Stripe IDs.
    This is an ATOMIC operation - if any record doesn't exist, aborts with no changes.
    
    Returns dict with 'plan' and 'price' objects if successful.
    Raises ValueError if records don't exist.
    """
    # Check if plan exists - if not, abort (atomic operation)
    plan = PaymentPlan.query.filter_by(code=PLAN_CODE, is_deleted=False).first()
    
    if not plan:
        raise ValueError(
            f"❌ Plan '{PLAN_CODE}' not found. "
            f"This script only UPDATES existing records - it does not create new ones. "
            f"Please create the plan first using the test seed script."
        )
    
    print(f"📝 Found existing plan: {plan.code} (ID: {plan.id})")
    
    # Check if price exists - if not, abort (atomic operation)
    price = PlanPrice.query.filter_by(key=PRICE_KEY, is_active=True).first()
    
    if not price:
        raise ValueError(
            f"❌ Price '{PRICE_KEY}' not found. "
            f"This script only UPDATES existing records - it does not create new ones. "
            f"Please create the price first using the test seed script."
        )
    
    print(f"📝 Found existing price: {price.key} (ID: {price.id})")
    
    # Verify price belongs to the plan
    if price.plan_id != plan.id:
        raise ValueError(
            f"❌ Price '{PRICE_KEY}' (plan_id: {price.plan_id}) does not belong to plan '{PLAN_CODE}' (id: {plan.id}). "
            f"Cannot proceed with atomic update."
        )
    
    print(f"✓ Price belongs to plan - proceeding with atomic update\n")
    
    # Update plan fields if needed
    plan_updated = False
    
    # Update stripe_product_id
    if plan.stripe_product_id != LIVE_STRIPE_PRODUCT_ID:
        old_product_id = plan.stripe_product_id
        plan.stripe_product_id = LIVE_STRIPE_PRODUCT_ID
        plan_updated = True
        print(f"🔄 Updating plan stripe_product_id:")
        print(f"   Old: {old_product_id}")
        print(f"   New: {LIVE_STRIPE_PRODUCT_ID}")
    
    # Update display_name
    if plan.display_name != PLAN_DISPLAY_NAME:
        old_display_name = plan.display_name
        plan.display_name = PLAN_DISPLAY_NAME
        plan_updated = True
        print(f"🔄 Updating plan display_name:")
        print(f"   Old: {old_display_name}")
        print(f"   New: {PLAN_DISPLAY_NAME}")
    
    # Update description
    if plan.description != PLAN_DESCRIPTION:
        old_description = plan.description
        plan.description = PLAN_DESCRIPTION
        plan_updated = True
        print(f"🔄 Updating plan description:")
        print(f"   Old: {old_description}")
        print(f"   New: {PLAN_DESCRIPTION}")
    
    # Update price fields if needed
    price_updated = False
    
    # Update stripe_price_id
    if price.stripe_price_id != LIVE_STRIPE_PRICE_ID:
        old_price_id = price.stripe_price_id
        price.stripe_price_id = LIVE_STRIPE_PRICE_ID
        price_updated = True
        print(f"🔄 Updating price stripe_price_id:")
        print(f"   Old: {old_price_id}")
        print(f"   New: {LIVE_STRIPE_PRICE_ID}")
    
    # Update stripe_overage_price_id
    if price.stripe_overage_price_id != LIVE_STRIPE_OVERAGE_PRICE_ID:
        old_overage_id = price.stripe_overage_price_id
        price.stripe_overage_price_id = LIVE_STRIPE_OVERAGE_PRICE_ID
        price_updated = True
        print(f"🔄 Updating price stripe_overage_price_id:")
        print(f"   Old: {old_overage_id}")
        print(f"   New: {LIVE_STRIPE_OVERAGE_PRICE_ID}")
    
    # Update nickname
    if price.nickname != PRICE_NICKNAME:
        old_nickname = price.nickname
        price.nickname = PRICE_NICKNAME
        price_updated = True
        print(f"🔄 Updating price nickname:")
        print(f"   Old: {old_nickname}")
        print(f"   New: {PRICE_NICKNAME}")
    
    # If nothing needs updating, inform user
    if not plan_updated and not price_updated:
        print("✓ All fields are already up to date - no changes needed")
    
    return {'plan': plan, 'price': price, 'plan_updated': plan_updated, 'price_updated': price_updated}


def main():
    """Main function to update payment plans with live Stripe IDs (UPDATE ONLY - no creates)."""
    print("\n" + "="*80)
    print("UPDATE PAYMENT PLANS - LIVE MODE (UPDATE ONLY)")
    print("="*80)
    print("\n⚠️  WARNING: This will UPDATE existing records with LIVE Stripe IDs.")
    print("⚠️  This script will NOT create new records - if records don't exist, it will abort.")
    print("⚠️  Make sure you have a database backup before proceeding!")
    print("\nLIVE Stripe IDs to be used:")
    print(f"   Product ID: {LIVE_STRIPE_PRODUCT_ID}")
    print(f"   Base Price ID: {LIVE_STRIPE_PRICE_ID}")
    print(f"   Overage Price ID: {LIVE_STRIPE_OVERAGE_PRICE_ID}")
    print("\nThis is an ATOMIC operation - all updates succeed or nothing changes.")
    print("="*80)
    
    confirm = input("\nDo you want to continue? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled. No changes made.")
        return 0
    
    app = create_app()
    with app.app_context():
        try:
            # Start transaction - all or nothing
            result = update_basic_plan_with_live_ids()
            
            # Check if any updates were made
            if not result.get('plan_updated') and not result.get('price_updated'):
                print("\n" + "="*80)
                print("ℹ️  NO CHANGES NEEDED")
                print("="*80)
                print("All Stripe IDs are already set to live values.")
                print("No database changes were made.")
                print("="*80 + "\n")
                return 0
            
            # Commit all changes atomically
            db.session.commit()
            
            print("\n" + "="*80)
            print("✅ SUCCESS - Database updated with LIVE Stripe IDs")
            print("="*80)
            print(f"\nPlan Details:")
            print(f"   ID: {result['plan'].id}")
            print(f"   Code: {result['plan'].code}")
            print(f"   Display Name: {result['plan'].display_name}")
            print(f"   Stripe Product ID: {result['plan'].stripe_product_id}")
            
            print(f"\nPrice Details:")
            print(f"   ID: {result['price'].id}")
            print(f"   Key: {result['price'].key}")
            print(f"   Stripe Price ID: {result['price'].stripe_price_id}")
            print(f"   Stripe Overage Price ID: {result['price'].stripe_overage_price_id}")
            print(f"   Currency: {result['price'].currency.upper()}")
            print(f"   Amount: {result['price'].amount_cents/100:.2f} {result['price'].currency.upper()}")
            print(f"   Per Seat: {result['price'].per_seat_amount_cents/100:.2f} {result['price'].currency.upper()}")
            print("="*80 + "\n")
            
            return 0
            
        except ValueError as e:
            # Validation error - records don't exist
            db.session.rollback()
            print(f"\n" + "="*80)
            print("❌ ABORTED - Records not found")
            print("="*80)
            print(f"{e}")
            print("\nThis script only UPDATES existing records.")
            print("Please ensure the plan and price exist before running this script.")
            print("="*80 + "\n")
            return 1
            
        except Exception as e:
            # Other errors
            db.session.rollback()
            print(f"\n" + "="*80)
            print("❌ ERROR - Transaction rolled back")
            print("="*80)
            print(f"Error: {e}")
            print("\nAll database changes have been rolled back (atomic operation).")
            print("="*80 + "\n")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == '__main__':
    sys.exit(main())

