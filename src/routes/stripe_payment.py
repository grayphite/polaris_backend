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
    """Get all active payment plans with their prices.
    
    Optional query parameter:
    - team_id: If provided, returns team-specific trial eligibility (has_used_trial)
    """
    team_id = request.args.get('team_id', type=int)
    team = None
    team_has_used_trial = False
    
    if team_id:
        team = Team.query.get(team_id)
        if team:
            team_has_used_trial = team.has_used_trial
    
    plans = PaymentPlan.query.filter_by(is_active=True, is_deleted=False).order_by(PaymentPlan.sort_order).all()
    
    result = []
    for plan in plans:
        prices = PlanPrice.query.filter_by(plan_id=plan.id, is_active=True).all()
        
        # Calculate trial eligibility for this team
        env_trial = os.getenv('TRIAL_PERIOD_DAYS')
        try:
            default_trial_days = int(env_trial) if env_trial is not None else 7
        except Exception:
            default_trial_days = 7
        
        eligible_trial_days = 0 if team_has_used_trial else default_trial_days
        
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
                'trial_days': price.trial_days,  # Default trial from plan
                'eligible_trial_days': eligible_trial_days,  # Team-specific trial eligibility
                'has_trial_available': eligible_trial_days > 0,  # Whether team can use trial
                'stripe_price_id': price.stripe_price_id,
                'per_seat_amount_cents': price.per_seat_amount_cents,
                'per_seat_metric': price.per_seat_metric,
            } for price in prices]
        })
    
    response = {'plans': result}
    if team_id:
        response['team_id'] = team_id
        response['team_has_used_trial'] = team_has_used_trial
    
    return jsonify(response)


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
    
    # If subscription status is incomplete, sync from Stripe to get latest status
    # This handles cases where webhooks were delayed or missed
    if subscription.status == 'incomplete' and subscription.stripe_subscription_id:
        try:
            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            stripe_status = stripe_sub.get('status', 'incomplete')
            
            # Update local status if it changed in Stripe
            if stripe_status != subscription.status:
                subscription.status = stripe_status
                # Update period dates if available
                if stripe_sub.get('current_period_start'):
                    subscription.current_period_start = datetime.fromtimestamp(stripe_sub['current_period_start'])
                if stripe_sub.get('current_period_end'):
                    subscription.current_period_end = datetime.fromtimestamp(stripe_sub['current_period_end'])
                db.session.commit()
                print(f'Synced subscription status from Stripe for team {team_id}: {stripe_status}')
        except Exception as e:
            print(f'Warning: Could not sync subscription status from Stripe: {e}')
            # Continue with local status if sync fails
    
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


@bp.route('/subscriptions/<int:team_id>/billing-summary', methods=['GET'])
def get_billing_summary(team_id):
    """Return current and upcoming invoices for a team's subscription."""
    try:
        result = StripePaymentService.get_upcoming_invoice_for_team(team_id, include_current_invoice=True)
        
        # Also include subscription status info for the frontend
        subscription = TeamSubscription.query.filter_by(
            team_id=team_id, 
            is_active=True, 
            is_deleted=False
        ).first()
        
        subscription_info = None
        if subscription:
            subscription_info = {
                'status': subscription.status,
                'cancel_at_period_end': subscription.cancel_at_period_end,
                'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
                'canceled_at': subscription.canceled_at.isoformat() if subscription.canceled_at else None,
            }
        
        return jsonify({
            'current_invoice': result.get('current_invoice'),
            'upcoming_invoice': result.get('invoice_data'),  # May be None if subscription is set to cancel
            'subscription': subscription_info
        })
    except ValueError as e:
        # Handle missing subscription or unlinked Stripe subscription
        return jsonify({'error': str(e)}), 404
    except stripe._error.StripeError as e:
        return jsonify({'error': f'Stripe error: {str(e)}'}), 400
    except Exception as e:
        print(f'Error fetching billing summary: {str(e)}')
        return jsonify({'error': f'Server error: {str(e)}'}), 500


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


@bp.route('/subscriptions/<int:team_id>/cancel', methods=['POST'])
def cancel_subscription(team_id):
    """Cancel a team's subscription (default: at period end)."""
    try:
        data = request.get_json(silent=True) or {}
        cancel_at_period_end = data.get('cancel_at_period_end', True)

        result = StripePaymentService.cancel_team_subscription(
            team_id=team_id,
            cancel_at_period_end=bool(cancel_at_period_end)
        )

        return jsonify({
            'success': True,
            'subscription': result
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except stripe._error.StripeError as e:
        return jsonify({'error': f'Stripe error: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@bp.route('/subscriptions/<int:team_id>/resume', methods=['POST'])
def resume_subscription(team_id):
    """Resume a subscription that was scheduled to cancel at period end."""
    try:
        result = StripePaymentService.resume_team_subscription(team_id)

        return jsonify({
            'success': True,
            'subscription': result
        })
    except ValueError as e:
        # Handle "not scheduled for cancellation" as 400, others as 404
        if 'not scheduled for cancellation' in str(e):
            return jsonify({'error': str(e)}), 400
        return jsonify({'error': str(e)}), 404
    except stripe._error.StripeError as e:
        return jsonify({'error': f'Stripe error: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


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
    if not price_id:
        return jsonify({'error': 'price_id is required'}), 400
    
    # Get team and team owner
    team = Team.query.get(team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404
    
    # Resolve trial days: skip trial if team has already used it
    trial_days = 0  # Default: no trial
    if not team.has_used_trial:
        # Team hasn't used trial yet - allow trial period
        env_trial = os.getenv('TRIAL_PERIOD_DAYS')
        try:
            trial_days = int(env_trial) if env_trial is not None else int(data.get('trial_days', 7))
        except Exception:
            trial_days = 7
    
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
        print(f"DEBUG: Trial days: {trial_days}, Team has_used_trial: {team.has_used_trial}")
        
        # Build subscription_data with conditional trial_period_days
        subscription_data = {
            'metadata': {
                'team_id': team_id,
                'billing_user_id': team_owner.id,
                'plan_id': price.plan_id,
                'price_id': price.id
            }
        }
        
        # Only add trial_period_days if team hasn't used trial yet
        if trial_days > 0:
            subscription_data['trial_period_days'] = int(trial_days)
        
        # Create checkout session
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
            subscription_data=subscription_data
        )
        
        return jsonify({
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id,
            'trial_days': trial_days if trial_days > 0 else 0,
            'has_trial': trial_days > 0,
            'team_has_used_trial': team.has_used_trial
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
    
    # Get subscription ID from checkout session if available
    subscription_id = session.get('subscription')
    payment_status = session.get('payment_status', 'unpaid')
    
    # Create or update local subscription record
    # For resubscriptions, Stripe creates a NEW subscription with a new ID
    # So we should check if this subscription_id already exists, or create new
    subscription = None
    
    # First, check if this specific Stripe subscription already exists
    if subscription_id:
        subscription = TeamSubscription.query.filter_by(
            stripe_subscription_id=subscription_id
        ).first()
    
    # If not found by subscription_id, check for active subscription for this team
    if not subscription:
        subscription = TeamSubscription.query.filter_by(
            team_id=int(team_id), 
            is_deleted=False,
            is_active=True
        ).first()
    
    # If still not found, this is likely a new subscription (resubscription after cancel)
    # Create a new subscription record instead of updating the old canceled one
    if not subscription:
        # Always fetch actual status from Stripe to ensure accuracy
        initial_status = 'incomplete'  # Default, will be updated from Stripe
        if subscription_id:
            try:
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                initial_status = stripe_sub.get('status', 'incomplete')
                print(f'Fetched subscription status from Stripe: {initial_status}')
            except Exception as e:
                print(f'Warning: Could not fetch subscription from Stripe: {e}')
                # Fallback based on payment_status
                initial_status = 'active' if payment_status == 'paid' else 'incomplete'
        
        subscription = TeamSubscription(
            team_id=int(team_id),
            billing_user_id=int(billing_user_id),
            plan_id=int(plan_id),
            price_id=int(price_id),
            stripe_customer_id=session.get('customer'),
            stripe_subscription_id=subscription_id,
            status=initial_status
        )
        
        # Set period dates if available from Stripe
        if subscription_id:
            try:
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                if stripe_sub.get('current_period_start'):
                    subscription.current_period_start = datetime.fromtimestamp(stripe_sub['current_period_start'])
                if stripe_sub.get('current_period_end'):
                    subscription.current_period_end = datetime.fromtimestamp(stripe_sub['current_period_end'])
            except Exception:
                pass
        
        db.session.add(subscription)
    else:
        # Update existing subscription
        # If this is a different subscription_id, it means it's a new subscription
        # In that case, mark old subscription as inactive and create new one
        if subscription_id and subscription.stripe_subscription_id and subscription.stripe_subscription_id != subscription_id:
            # This is a new subscription (resubscription), mark old one as inactive
            old_subscription = subscription
            old_subscription.is_active = False
            db.session.flush()
            
            # Create new subscription record - always fetch status from Stripe
            initial_status = 'incomplete'
            if subscription_id:
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription_id)
                    initial_status = stripe_sub.get('status', 'incomplete')
                except Exception as e:
                    print(f'Warning: Could not fetch subscription status: {e}')
                    initial_status = 'active' if payment_status == 'paid' else 'incomplete'
            
            subscription = TeamSubscription(
                team_id=int(team_id),
                billing_user_id=int(billing_user_id),
                plan_id=int(plan_id),
                price_id=int(price_id),
                stripe_customer_id=session.get('customer'),
                stripe_subscription_id=subscription_id,
                status=initial_status,
                is_active=True
            )
            
            # Set period dates if available
            if subscription_id:
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription_id)
                    if stripe_sub.get('current_period_start'):
                        subscription.current_period_start = datetime.fromtimestamp(stripe_sub['current_period_start'])
                    if stripe_sub.get('current_period_end'):
                        subscription.current_period_end = datetime.fromtimestamp(stripe_sub['current_period_end'])
                except Exception:
                    pass
            
            db.session.add(subscription)
            print(f'Created new subscription record for resubscription, team {team_id}, status: {initial_status}')
        else:
            # Update existing subscription (same subscription_id)
            if subscription_id:
                subscription.stripe_subscription_id = subscription_id
            
            # Reactivate if it was previously canceled
            if subscription.status == 'canceled':
                subscription.status = 'incomplete'  # Will be updated by Stripe status
                subscription.canceled_at = None
                subscription.cancel_at_period_end = False
                subscription.is_active = True
                print(f'Reactivating canceled subscription for team {team_id}')
        
        # Always sync status from Stripe when subscription_id is available
        # This ensures we have the actual subscription status, not just payment_status
        if subscription_id:
            try:
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                stripe_status = stripe_sub.get('status', subscription.status)
                subscription.status = stripe_status
                subscription.is_active = True  # Ensure it's marked as active
                # Update period dates from Stripe
                if stripe_sub.get('current_period_start'):
                    subscription.current_period_start = datetime.fromtimestamp(stripe_sub['current_period_start'])
                if stripe_sub.get('current_period_end'):
                    subscription.current_period_end = datetime.fromtimestamp(stripe_sub['current_period_end'])
                print(f'Synced subscription status from Stripe in checkout.completed: {stripe_status}')
            except Exception as e:
                print(f'Warning: Could not fetch subscription from Stripe in checkout.completed: {e}')
                # Fallback: if payment_status is paid, assume active
                if payment_status == 'paid' and subscription.status in ['incomplete', 'canceled']:
                    subscription.status = 'active'
                    subscription.is_active = True
    
    db.session.commit()
    print(f'Checkout completed for team {team_id}, payment_status: {payment_status}, status: {subscription.status}')


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
        stripe_status = subscription.get('status', 'incomplete')
        local_subscription.stripe_subscription_id = subscription.get('id')
        local_subscription.status = stripe_status  # Always use status from Stripe
        cps = subscription.get('current_period_start')
        cpe = subscription.get('current_period_end')
        te = subscription.get('trial_end')
        local_subscription.current_period_start = datetime.fromtimestamp(cps) if cps else None
        local_subscription.current_period_end = datetime.fromtimestamp(cpe) if cpe else None
        local_subscription.trial_end = datetime.fromtimestamp(te) if te else None
        local_subscription.quantity = subscription.get('quantity', local_subscription.quantity or 1)
        
        # Mark team as having used trial if trial_end exists
        if te:
            team = Team.query.get(int(team_id))
            if team and not team.has_used_trial:
                team.has_used_trial = True
                print(f'Marked team {team_id} as having used trial')
        
        # If subscription is active in Stripe but local status is incomplete, update it
        # This handles the case where payment succeeded but webhook order was different
        if stripe_status == 'active' and local_subscription.status == 'incomplete':
            local_subscription.status = 'active'
            print(f'Updated subscription status from incomplete to active for team {team_id}')
        
        db.session.commit()
        print(f'Subscription created/linked for team {team_id}, status: {local_subscription.status}')
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
            # Update status to active when payment succeeds (especially for subscriptions without trial)
            # This handles the case where subscription was "incomplete" and payment just succeeded
            if local_subscription.status in ['incomplete', 'trialing']:
                # Fetch current status from Stripe to ensure accuracy
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription_id)
                    local_subscription.status = stripe_sub.get('status', 'active')
                    # Update period dates from Stripe
                    if stripe_sub.get('current_period_start'):
                        local_subscription.current_period_start = datetime.fromtimestamp(stripe_sub['current_period_start'])
                    if stripe_sub.get('current_period_end'):
                        local_subscription.current_period_end = datetime.fromtimestamp(stripe_sub['current_period_end'])
                except Exception as e:
                    # Fallback: set to active if we can't fetch from Stripe
                    print(f'Warning: Could not fetch subscription from Stripe: {e}')
                    local_subscription.status = 'active'
            
            db.session.commit()
            print(f'Payment succeeded for subscription: {subscription_id}, status updated to: {local_subscription.status}')


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


