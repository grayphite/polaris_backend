"""
Stripe payment service skeleton.

Contains helpers to manage plan catalog and team subscriptions.
Implementation will be filled after model review and migrations.
"""
import os
from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any

import stripe

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
                stripe_overage_price_id='price_1SOEJOAIZic08EhhMj7DdWST',
                is_active=True
            )
            db.session.add(price)
        else:
            # Ensure overage price is populated
            if not getattr(price, 'stripe_overage_price_id', None):
                price.stripe_overage_price_id = 'price_1SOEJOAIZic08EhhMj7DdWST'

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

    @staticmethod
    def get_upcoming_invoice_for_team(team_id: int, include_current_invoice: bool = False) -> Dict[str, Any]:
        """
        Fetch and format the upcoming invoice for a team's subscription.
        
        Args:
            team_id: The ID of the team to fetch the invoice for
            
        Returns:
            Dictionary with 'invoice_data' key containing formatted invoice data,
            or 'error' key with error message if something went wrong
            
        Raises:
            ValueError: If subscription is not found or not linked to Stripe
            stripe._error.StripeError: For Stripe API errors
        """
        # Get the active subscription
        subscription = TeamSubscription.query.filter_by(
            team_id=team_id, 
            is_active=True, 
            is_deleted=False
        ).first()
        
        if not subscription:
            raise ValueError('No active subscription found')
        
        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription not linked to Stripe')
        
        # Ensure Stripe API key is set
        if not getattr(stripe, 'api_key', None):
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        
        # Try to fetch the upcoming invoice from Stripe
        # This may fail if subscription is set to cancel at period end
        upcoming_invoice = None
        invoice_data = None
        
        try:
            upcoming_invoice = stripe.Invoice.upcoming(
                subscription=subscription.stripe_subscription_id
            )
            
            # Format line items
            line_items = []
            for item in upcoming_invoice.get('lines', {}).get('data', []):
                line_items.append({
                    'id': item.get('id'),
                    'description': item.get('description', ''),
                    'amount': item.get('amount', 0),
                    'currency': item.get('currency', 'brl'),
                    'quantity': item.get('quantity', 1),
                    'price': {
                        'id': item.get('price', {}).get('id'),
                        'nickname': item.get('price', {}).get('nickname', ''),
                        'unit_amount': item.get('price', {}).get('unit_amount', 0),
                        'currency': item.get('price', {}).get('currency', 'brl'),
                    } if item.get('price') else None,
                    'period': {
                        'start': datetime.fromtimestamp(item.get('period', {}).get('start', 0), UTC).isoformat() if item.get('period', {}).get('start') else None,
                        'end': datetime.fromtimestamp(item.get('period', {}).get('end', 0), UTC).isoformat() if item.get('period', {}).get('end') else None,
                    } if item.get('period') else None,
                    'proration': item.get('proration', False),
                })
            
            # Format the response
            invoice_data = {
                'invoice_id': upcoming_invoice.get('id'),  # May be None for upcoming invoices
                'subscription_id': upcoming_invoice.get('subscription'),
                'customer_id': upcoming_invoice.get('customer'),
                'amount_due': upcoming_invoice.get('amount_due', 0),
                'amount_paid': upcoming_invoice.get('amount_paid', 0),
                'amount_remaining': upcoming_invoice.get('amount_remaining', 0),
                'subtotal': upcoming_invoice.get('subtotal', 0),
                'total': upcoming_invoice.get('total', 0),
                'currency': upcoming_invoice.get('currency', 'brl').upper(),
                'period_start': datetime.fromtimestamp(upcoming_invoice.get('period_start', 0), UTC).isoformat() if upcoming_invoice.get('period_start') else None,
                'period_end': datetime.fromtimestamp(upcoming_invoice.get('period_end', 0), UTC).isoformat() if upcoming_invoice.get('period_end') else None,
                'next_payment_attempt': datetime.fromtimestamp(upcoming_invoice.get('next_payment_attempt', 0), UTC).isoformat() if upcoming_invoice.get('next_payment_attempt') else None,
                'status': upcoming_invoice.get('status'),
                'line_items': line_items,
                'discount': {
                    'id': upcoming_invoice.get('discount', {}).get('id'),
                    'coupon_id': upcoming_invoice.get('discount', {}).get('coupon', {}).get('id') if upcoming_invoice.get('discount', {}).get('coupon') else None,
                    'amount_off': upcoming_invoice.get('discount', {}).get('coupon', {}).get('amount_off', 0) if upcoming_invoice.get('discount', {}).get('coupon') else None,
                    'percent_off': upcoming_invoice.get('discount', {}).get('coupon', {}).get('percent_off', 0) if upcoming_invoice.get('discount', {}).get('coupon') else None,
                } if upcoming_invoice.get('discount') else None,
                'tax': upcoming_invoice.get('tax', 0),
                'has_proration': any(item.get('proration', False) for item in line_items),
            }
        except stripe._error.InvalidRequestError as e:
            # If subscription is set to cancel, there may be no upcoming invoice
            # This is expected behavior - we'll return null for upcoming_invoice
            if 'No upcoming invoices' in str(e) or 'No such subscription' in str(e):
                invoice_data = None
            else:
                # Re-raise other InvalidRequestErrors
                raise
        except Exception as e:
            # Log but don't fail - we'll still return current invoice
            print(f'Warning: Could not fetch upcoming invoice: {str(e)}')
            invoice_data = None
        
        result: Dict[str, Any] = {'invoice_data': invoice_data}

        if include_current_invoice:
            try:
                current = stripe.Invoice.list(subscription=subscription.stripe_subscription_id, limit=1)
                current_invoice_obj = current['data'][0] if current and current.get('data') else None
            except Exception:
                current_invoice_obj = None

            if current_invoice_obj:
                # Format current invoice similarly (lines may be summarized; keep key fields)
                current_line_items = []
                for item in current_invoice_obj.get('lines', {}).get('data', []):
                    current_line_items.append({
                        'id': item.get('id'),
                        'description': item.get('description', ''),
                        'amount': item.get('amount', 0),
                        'currency': item.get('currency', 'brl'),
                        'quantity': item.get('quantity', 1),
                        'price': {
                            'id': item.get('price', {}).get('id'),
                            'nickname': item.get('price', {}).get('nickname', ''),
                            'unit_amount': item.get('price', {}).get('unit_amount', 0),
                            'currency': item.get('price', {}).get('currency', 'brl'),
                        } if item.get('price') else None,
                        'period': {
                            'start': datetime.fromtimestamp(item.get('period', {}).get('start', 0), UTC).isoformat() if item.get('period', {}).get('start') else None,
                            'end': datetime.fromtimestamp(item.get('period', {}).get('end', 0), UTC).isoformat() if item.get('period', {}).get('end') else None,
                        } if item.get('period') else None,
                        'proration': item.get('proration', False),
                    })

                result['current_invoice'] = {
                    'invoice_id': current_invoice_obj.get('id'),
                    'subscription_id': current_invoice_obj.get('subscription'),
                    'customer_id': current_invoice_obj.get('customer'),
                    'amount_due': current_invoice_obj.get('amount_due', 0),
                    'amount_paid': current_invoice_obj.get('amount_paid', 0),
                    'amount_remaining': current_invoice_obj.get('amount_remaining', 0),
                    'subtotal': current_invoice_obj.get('subtotal', 0),
                    'total': current_invoice_obj.get('total', 0),
                    'currency': (current_invoice_obj.get('currency') or 'brl').upper(),
                    'period_start': datetime.fromtimestamp(current_invoice_obj.get('period_start', 0), UTC).isoformat() if current_invoice_obj.get('period_start') else None,
                    'period_end': datetime.fromtimestamp(current_invoice_obj.get('period_end', 0), UTC).isoformat() if current_invoice_obj.get('period_end') else None,
                    'status': current_invoice_obj.get('status'),
                    'hosted_invoice_url': current_invoice_obj.get('hosted_invoice_url'),
                    'invoice_pdf': current_invoice_obj.get('invoice_pdf'),
                    'line_items': current_line_items,
                }
            else:
                result['current_invoice'] = None

        return result



    @staticmethod
    def cancel_team_subscription(team_id: int, cancel_at_period_end: bool = True) -> Dict[str, Any]:
        """
        Cancel a team's active subscription either immediately or at period end.

        Args:
            team_id: Team identifier
            cancel_at_period_end: If True, set cancel_at_period_end on Stripe; if False, cancel immediately

        Returns:
            Dict with keys: status, cancel_at_period_end, current_period_end, canceled_at

        Raises:
            ValueError for missing subscription or Stripe linkage
            stripe._error.StripeError for Stripe API errors
        """
        subscription = TeamSubscription.query.filter_by(
            team_id=team_id, is_active=True, is_deleted=False
        ).first()

        if not subscription:
            raise ValueError('No active subscription found')

        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription not linked to Stripe')

        # Ensure Stripe API key
        if not getattr(stripe, 'api_key', None):
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

        if cancel_at_period_end:
            stripe_sub = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            subscription.cancel_at_period_end = True
            # Keep status as-is; Stripe will mark at period end
        else:
            stripe_sub = stripe.Subscription.delete(subscription.stripe_subscription_id)
            subscription.status = 'canceled'
            subscription.is_active = False  # Deactivate immediately canceled subscriptions
            subscription.canceled_at = datetime.now(UTC)

        # Reflect period end if present
        try:
            cpe = stripe_sub.get('current_period_end') if isinstance(stripe_sub, dict) else getattr(stripe_sub, 'current_period_end', None)
            if cpe:
                subscription.current_period_end = datetime.fromtimestamp(cpe)
        except Exception:
            pass

        db.session.commit()

        return {
            'status': subscription.status,
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            'canceled_at': subscription.canceled_at.isoformat() if subscription.canceled_at else None,
        }

    @staticmethod
    def resume_team_subscription(team_id: int) -> Dict[str, Any]:
        """
        Resume a subscription that was scheduled to cancel at period end.
        Removes the cancel_at_period_end flag, allowing the subscription to continue.

        Args:
            team_id: Team identifier

        Returns:
            Dict with keys: status, cancel_at_period_end, current_period_end, canceled_at

        Raises:
            ValueError if subscription not found, not linked to Stripe, or not scheduled for cancellation
            stripe._error.StripeError for Stripe API errors
        """
        subscription = TeamSubscription.query.filter_by(
            team_id=team_id, is_active=True, is_deleted=False
        ).first()

        if not subscription:
            raise ValueError('No active subscription found')

        if not subscription.stripe_subscription_id:
            raise ValueError('Subscription not linked to Stripe')

        if not subscription.cancel_at_period_end:
            raise ValueError('Subscription is not scheduled for cancellation')

        # Ensure Stripe API key
        if not getattr(stripe, 'api_key', None):
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

        # Remove cancel_at_period_end flag
        stripe_sub = stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=False
        )

        # Update local subscription
        subscription.cancel_at_period_end = False
        subscription.canceled_at = None  # Clear canceled_at since we're resuming

        # Update period end from Stripe if available
        try:
            cpe = stripe_sub.get('current_period_end') if isinstance(stripe_sub, dict) else getattr(stripe_sub, 'current_period_end', None)
            if cpe:
                subscription.current_period_end = datetime.fromtimestamp(cpe)
        except Exception:
            pass

        db.session.commit()

        return {
            'status': subscription.status,
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            'canceled_at': subscription.canceled_at.isoformat() if subscription.canceled_at else None,
        }
