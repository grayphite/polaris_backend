"""
Stripe payment routes with real Stripe integration.

Endpoints for checkout, webhooks, and subscription management.
"""
import os
import stripe
from datetime import datetime, UTC
from flask import Blueprint, jsonify, request
from src.extensions import db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.services.payment_services.stripe_payment_service import StripePaymentService
from src.services.payment_services.usage_billing_service import UsageBillingService
from src.models import PaymentPlan, PlanPrice, TeamSubscription, Team, TeamMember, User

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

bp = Blueprint('stripe_payment', __name__, url_prefix='/api')


@bp.route('/plans', methods=['GET'])
def get_plans():
    """Get all active payment plans with their prices."""
    plans = PaymentPlan.query.filter_by(is_active=True, is_deleted=False).order_by(PaymentPlan.sort_order).all()
    
    result = []
    for plan in plans:
        prices = PlanPrice.query.filter_by(plan_id=plan.id, is_active=True).all()
        result.append({
            'id': plan.id,
            'code': plan.code,
            'display_name': plan.display_name,
            'description': plan.description,
            'max_teams': plan.max_teams,
            'max_projects': plan.max_projects,
            'max_team_members_per_team': plan.max_team_members_per_team,
            'max_project_members_per_project': plan.max_project_members_per_project,
            'can_add_users_to_project': plan.can_add_users_to_project,
            'features': plan.features,
            'prices': [{
                'id': price.id,
                'key': price.key,
                'nickname': price.nickname,
                'currency': price.currency,
                'amount_cents': price.amount_cents,
                'compare_at_cents': price.compare_at_cents,
                'interval': price.interval,
                'interval_count': price.interval_count,
                'trial_days': price.trial_days,
                'stripe_price_id': price.stripe_price_id,
                'per_seat_amount_cents': price.per_seat_amount_cents,
                'per_seat_metric': price.per_seat_metric,
            } for price in prices]
        })
    
    return jsonify({'plans': result})


@bp.route('/subscriptions/<int:team_id>', methods=['GET'])
def get_team_subscription(team_id):
    """Get team's active subscription details."""
    subscription = TeamSubscription.query.filter_by(
        team_id=team_id, 
        is_active=True, 
        is_deleted=False
    ).first()
    
    if not subscription:
        return jsonify({'error': 'No active subscription found'}), 404
    
    return jsonify({
        'subscription': {
            'id': subscription.id,
            'team_id': subscription.team_id,
            'billing_user_id': subscription.billing_user_id,
            'status': subscription.status,
            'quantity': subscription.quantity,
            'trial_end': subscription.trial_end.isoformat() if subscription.trial_end else None,
            'current_period_start': subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'canceled_at': subscription.canceled_at.isoformat() if subscription.canceled_at else None,
            'plan': {
                'id': subscription.plan.id,
                'code': subscription.plan.code,
                'display_name': subscription.plan.display_name,
                'max_teams': subscription.plan.max_teams,
                'max_projects': subscription.plan.max_projects,
                'max_team_members_per_team': subscription.plan.max_team_members_per_team,
                'max_project_members_per_project': subscription.plan.max_project_members_per_project,
                'can_add_users_to_project': subscription.plan.can_add_users_to_project,
                'features': subscription.plan.features,
            },
            'price': {
                'id': subscription.price.id,
                'key': subscription.price.key,
                'nickname': subscription.price.nickname,
                'currency': subscription.price.currency,
                'amount_cents': subscription.price.amount_cents,
                'interval': subscription.price.interval,
                'trial_days': subscription.price.trial_days,
                'per_seat_amount_cents': subscription.price.per_seat_amount_cents,
                'per_seat_metric': subscription.price.per_seat_metric,
            }
        }
    })


@bp.route('/subscriptions/<int:team_id>/members/preview', methods=['POST'])
def preview_member_addition(team_id):
    """Preview cost of adding a team member."""
    validation = UsageBillingService.validate_can_add_team_member(team_id)
    
    # Always return the same response structure with allowed flag
    return jsonify({
        'allowed': validation.get('allowed', False),
        'will_be_overage': validation.get('will_be_overage', False),
        'additional_member_cost_cents': validation.get('additional_member_cost_cents', 0),
        'currency': validation.get('currency', 'brl'),
        'current_active_members': validation.get('current_active_members', 0),
        'included_members_in_plan': validation.get('included_members_in_plan', 0),
        'additional_members': validation.get('additional_members', 0)
    }), 200


@bp.route('/subscriptions/<int:team_id>/members/add', methods=['POST'])
def add_team_member_with_billing(team_id):
    """Add a team member with billing check."""
    data = request.get_json()
    user_id = data.get('user_id')
    added_by = data.get('added_by')  # User adding the member
    
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    
    if not added_by:
        return jsonify({'error': 'added_by is required'}), 400
    
    result = UsageBillingService.add_team_member_with_billing_check(team_id, user_id, added_by)
    
    if not result.get('success'):
        return jsonify({'error': result.get('error')}), 400
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'member_id': result.get('member_id'),
        'billing_intent': result.get('billing_intent')
    })


@bp.route('/stripe/checkout/<int:team_id>', methods=['POST'])
def create_checkout_session(team_id):
    """Create Stripe checkout session for team subscription."""
    data = request.get_json()
    price_id = data.get('price_id')
    # Resolve trial days: prefer env TRIAL_PERIOD_DAYS, fallback to body, then 7
    env_trial = os.getenv('TRIAL_PERIOD_DAYS')
    try:
        trial_days = int(env_trial) if env_trial is not None else int(data.get('trial_days', 7))
    except Exception:
        trial_days = 7
    
    if not price_id:
        return jsonify({'error': 'price_id is required'}), 400
    
    # Get team and team owner
    team = Team.query.get(team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404
    
    print(f"DEBUG: Found team: {team.name}, created_by: {team.created_by}")
    
    team_owner = User.query.get(team.created_by)
    if not team_owner:
        return jsonify({'error': 'Team owner not found'}), 404
    
    print(f"DEBUG: Found team owner: {team_owner.email}, name: {team_owner.first_name} {team_owner.last_name}")
    
    # Get price details
    price = PlanPrice.query.filter_by(stripe_price_id=price_id, is_active=True).first()
    if not price:
        return jsonify({'error': 'Price not found'}), 404
    
    try:
        # Check Stripe API key
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        print(f"DEBUG: Stripe API key set: {bool(stripe_key)}")
        if stripe_key:
            print(f"DEBUG: Stripe API key starts with: {stripe_key[:7]}...")
        
        # Get URLs with proper fallbacks
        success_url = os.getenv('FRONTEND_SUCCESS_URL') or 'https://polaris-dev.grayphite.com/success'
        cancel_url = os.getenv('FRONTEND_CANCEL_URL') or 'https://polaris-dev.grayphite.com/cancel'
        
        # Ensure URLs have proper scheme
        if not success_url.startswith(('http://', 'https://')):
            success_url = f'https://{success_url}'
        if not cancel_url.startswith(('http://', 'https://')):
            cancel_url = f'https://{cancel_url}'
            
        print(f"DEBUG: Success URL: {success_url}")
        print(f"DEBUG: Cancel URL: {cancel_url}")
        
        # Create checkout session without customer for now
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'team_id': team_id,
                'billing_user_id': team_owner.id,
                'plan_id': price.plan_id,
                'price_id': price.id
            },
            subscription_data={
                'metadata': {
                    'team_id': team_id,
                    'billing_user_id': team_owner.id,
                    'plan_id': price.plan_id,
                    'price_id': price.id
                },
                'trial_period_days': int(trial_days)
            }
        )
        
        return jsonify({
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id
        })
        
    except stripe._error.StripeError as e:
        return jsonify({'error': f'Stripe error: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        return jsonify({'error': 'Webhook secret not configured'}), 500
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        return jsonify({'error': f'Invalid payload: {str(e)}'}), 400
    except stripe._error.SignatureVerificationError as e:
        return jsonify({'error': f'Invalid signature: {str(e)}'}), 400
    
    # Handle the event (defensive - never 500 to Stripe)
    try:
        if event['type'] == 'checkout.session.completed':
            handle_checkout_completed(event['data']['object'])
        elif event['type'] == 'customer.subscription.created':
            handle_subscription_created(event['data']['object'])
        elif event['type'] == 'customer.subscription.updated':
            handle_subscription_updated(event['data']['object'])
        elif event['type'] == 'customer.subscription.deleted':
            handle_subscription_deleted(event['data']['object'])
        elif event['type'] == 'invoice.payment_succeeded':
            handle_payment_succeeded(event['data']['object'])
        elif event['type'] == 'invoice.payment_failed':
            handle_payment_failed(event['data']['object'])
        else:
            print(f'Unhandled event type: {event["type"]}')
    except Exception as e:
        # Log and still return 200 so Stripe stops retrying
        print(f'ERROR handling webhook {event.get("type")}: {e}')
    
    return jsonify({'status': 'success'})


def handle_checkout_completed(session):
    """Handle successful checkout session."""
    metadata = session.get('metadata', {})
    team_id = metadata.get('team_id')
    billing_user_id = metadata.get('billing_user_id')
    plan_id = metadata.get('plan_id')
    price_id = metadata.get('price_id')
    
    if not all([team_id, billing_user_id, plan_id, price_id]):
        print(f'Missing metadata in checkout session: {session["id"]}')
        return
    
    # Create local subscription record
    subscription = TeamSubscription.query.filter_by(
        team_id=int(team_id), 
        is_deleted=False
    ).first()
    
    if not subscription:
        subscription = TeamSubscription(
            team_id=int(team_id),
            billing_user_id=int(billing_user_id),
            plan_id=int(plan_id),
            price_id=int(price_id),
            stripe_customer_id=session.get('customer'),
            status='trialing'  # Will be updated by subscription webhook
        )
        db.session.add(subscription)
    
    db.session.commit()
    print(f'Checkout completed for team {team_id}')


def handle_subscription_created(subscription):
    """Handle new subscription creation (idempotent upsert)."""
    try:
        metadata = subscription.get('metadata', {})
        team_id = metadata.get('team_id')
        
        if not team_id:
            print(f'Missing team_id in subscription metadata: {subscription.get("id")}')
            return
        
        # Find by team (normal case - created after checkout) or by stripe id
        local_subscription = TeamSubscription.query.filter_by(
            team_id=int(team_id), 
            is_deleted=False
        ).first()
        
        if not local_subscription:
            # Fallback: try by stripe id (replays, out-of-order)
            local_subscription = TeamSubscription.query.filter_by(
                stripe_subscription_id=subscription.get('id')
            ).first()
        
        if not local_subscription:
            # As a safety net, create a minimal local record from metadata
            local_subscription = TeamSubscription(
                team_id=int(team_id),
                billing_user_id=int(metadata.get('billing_user_id')) if metadata.get('billing_user_id') else None,
                plan_id=int(metadata.get('plan_id')) if metadata.get('plan_id') else None,
                price_id=int(metadata.get('price_id')) if metadata.get('price_id') else None,
            )
            db.session.add(local_subscription)
            db.session.flush()
        
        # Update fields from Stripe
        local_subscription.stripe_subscription_id = subscription.get('id')
        local_subscription.status = subscription.get('status', local_subscription.status)
        cps = subscription.get('current_period_start')
        cpe = subscription.get('current_period_end')
        te = subscription.get('trial_end')
        local_subscription.current_period_start = datetime.fromtimestamp(cps) if cps else None
        local_subscription.current_period_end = datetime.fromtimestamp(cpe) if cpe else None
        local_subscription.trial_end = datetime.fromtimestamp(te) if te else None
        local_subscription.quantity = subscription.get('quantity', local_subscription.quantity or 1)
        
        db.session.commit()
        print(f'Subscription created/linked for team {team_id}')
    except Exception as e:
        db.session.rollback()
        print(f'ERROR in handle_subscription_created: {e}')


def handle_subscription_updated(subscription):
    """Handle subscription updates."""
    metadata = subscription.get('metadata', {})
    team_id = metadata.get('team_id')
    
    if not team_id:
        print(f'Missing team_id in subscription metadata: {subscription["id"]}')
        return
    
    # Update local subscription
    local_subscription = TeamSubscription.query.filter_by(
        stripe_subscription_id=subscription['id']
    ).first()
    
    if local_subscription:
        local_subscription.status = subscription['status']
        local_subscription.trial_end = datetime.fromtimestamp(subscription.get('trial_end')) if subscription.get('trial_end') else None
        local_subscription.current_period_start = datetime.fromtimestamp(subscription['current_period_start'])
        local_subscription.current_period_end = datetime.fromtimestamp(subscription['current_period_end'])
        local_subscription.quantity = subscription.get('quantity', 1)
        local_subscription.cancel_at_period_end = subscription.get('cancel_at_period_end', False)
        
        if subscription.get('canceled_at'):
            local_subscription.canceled_at = datetime.fromtimestamp(subscription['canceled_at'])
        
        db.session.commit()
        print(f'Subscription updated for team {team_id}')


def handle_subscription_deleted(subscription):
    """Handle subscription cancellation."""
    local_subscription = TeamSubscription.query.filter_by(
        stripe_subscription_id=subscription['id']
    ).first()
    
    if local_subscription:
        local_subscription.status = 'canceled'
        local_subscription.canceled_at = datetime.fromtimestamp(subscription.get('canceled_at', datetime.now().timestamp()))
        db.session.commit()
        print(f'Subscription canceled: {subscription["id"]}')


def handle_payment_succeeded(invoice):
    """Handle successful payment."""
    subscription_id = invoice.get('subscription')
    if subscription_id:
        local_subscription = TeamSubscription.query.filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        
        if local_subscription:
            local_subscription.stripe_latest_invoice_id = invoice['id']
            db.session.commit()
            print(f'Payment succeeded for subscription: {subscription_id}')


def handle_payment_failed(invoice):
    """Handle failed payment."""
    subscription_id = invoice.get('subscription')
    if subscription_id:
        local_subscription = TeamSubscription.query.filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        
        if local_subscription:
            local_subscription.status = 'past_due'
            local_subscription.stripe_latest_invoice_id = invoice['id']
            db.session.commit()
            print(f'Payment failed for subscription: {subscription_id}')


@bp.route('/stripe/catalog/basic/ensure', methods=['POST'])
def ensure_basic_catalog():
    """Create Basic plan + price in local catalog (no commit)."""
    result = StripePaymentService.ensure_basic_plan_catalog()
    plan = result['plan']
    price = result['price']
    return jsonify({
        'plan': {
            'id': plan.id,
            'code': plan.code,
            'display_name': plan.display_name,
            'stripe_product_id': plan.stripe_product_id,
            'max_teams': plan.max_teams,
            'max_projects': plan.max_projects,
            'max_team_members_per_team': plan.max_team_members_per_team,
            'max_project_members_per_project': plan.max_project_members_per_project,
            'can_add_users_to_project': plan.can_add_users_to_project,
        },
        'price': {
            'id': price.id,
            'key': price.key,
            'nickname': price.nickname,
            'currency': price.currency,
            'amount_cents': price.amount_cents,
            'interval': price.interval,
            'trial_days': price.trial_days,
            'stripe_price_id': price.stripe_price_id,
            'per_seat_amount_cents': price.per_seat_amount_cents,
        }
    })


