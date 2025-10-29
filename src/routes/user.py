from flask import Blueprint, jsonify, request, g

from src.extensions import db
from src.models.user import User
from src.services.auth_service import auth_service
from src.models import TeamSubscription

user_bp = Blueprint('user', __name__)


@user_bp.route('/users/register', methods=['POST'])
def register_user():
    """Registra um novo usuário"""
    try:
        data = request.json

        # Validar dados obrigatórios
        if not data.get('email') or not data.get('senha'):
            return jsonify({'error': 'Email e senha são obrigatórios'}), 400

        # Registrar usuário via AuthService
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        invitation_token = data.get('invitation_token')  # Optional invitation token
        
        # Normalize invitation_token (handle empty string, None, etc.)
        if invitation_token and isinstance(invitation_token, str):
            invitation_token = invitation_token.strip()
            invitation_token = invitation_token if invitation_token else None
        else:
            invitation_token = None

        # If invitation token provided, verify invitation before registration
        invitation = None
        user_role = 'owner'  # Default to 'owner' if no invitation token
        
        if invitation_token:
            from src.models.invitation import Invitation
            invitation = Invitation.get_by_token(invitation_token)
            
            if not invitation:
                return jsonify({'error': 'Convite não encontrado - token inválido ou expirado'}), 400
            
            if not invitation.can_be_accepted():
                return jsonify({'error': 'Convite não pode ser aceito (expirado ou já processado)'}), 400
            
            # Verify email matches invitation
            if data['email'].lower().strip() != invitation.invited_email.lower().strip():
                return jsonify({'error': 'Email não corresponde ao convite enviado'}), 400
            
            # Set role from invitation (should be 'member' for invited users)
            user_role = invitation.role if invitation.role else 'member'

        result = auth_service.register_user(
            username=data['email'],  # Usar email como username
            email=data['email'],
            password=data['senha'],
            first_name=first_name,
            last_name=last_name,
            role=user_role  # Set role from invitation or default
        )

        if not result.success:
            return jsonify({'error': result.error}), 400

        # If invitation token provided, process invitation acceptance
        if invitation_token and invitation:
            try:
                from src.services.team_service import team_service
                from src.services.payment_services.usage_billing_service import UsageBillingService
                
                # Accept invitation (update status)
                invitation.accept(result.user['id'])
                db.session.add(invitation)
                
                # Add user to team with role from invitation
                add_result = team_service.add_team_member(
                    team_id=invitation.team_id,
                    user_id=invitation.inviter_id,  # Use inviter as the one adding
                    member_user_id=result.user['id'],
                    role=invitation.role,  # Use role from invitation
                    added_by=invitation.inviter_id
                )
                
                if not add_result.success:
                    # Rollback invitation acceptance
                    invitation.status = 'pending'
                    invitation.responded_at = None
                    invitation.accepted_at = None
                    invitation.invited_user_id = None
                    db.session.rollback()
                    return jsonify({'error': f'Falha ao adicionar usuário ao time: {add_result.error}'}), 400
                
                # Sync subscription quantity with Stripe if needed (for overage billing)
                # This checks if quantity needs updating and prepares for Stripe sync
                UsageBillingService.sync_subscription_quantity_with_stripe(invitation.team_id)
                
                # Commit invitation acceptance and team membership
                db.session.commit()
                
            except Exception as e:
                db.session.rollback()
                # Log error but don't fail registration - user is already registered
                print(f"Error processing invitation: {str(e)}")
                # User is registered but invitation processing failed
                # They can manually accept invitation later

        # Build team_subscriptions list for this user (if billing owner)
        ts_obj = []
        try:
            subscriptions = TeamSubscription.query.filter_by(
                billing_user_id=result.user['id'], 
                is_deleted=False
            ).all()
            
            for ts in subscriptions:
                ts_obj.append({
                    'id': ts.id,
                    'team_id': ts.team_id,
                    'billing_user_id': ts.billing_user_id,
                    'status': ts.status,
                    'quantity': ts.quantity,
                    'trial_end': ts.trial_end.isoformat() if ts.trial_end else None,
                    'current_period_start': ts.current_period_start.isoformat() if ts.current_period_start else None,
                    'current_period_end': ts.current_period_end.isoformat() if ts.current_period_end else None,
                    'cancel_at_period_end': ts.cancel_at_period_end,
                    'canceled_at': ts.canceled_at.isoformat() if ts.canceled_at else None,
                    'plan': {
                        'id': ts.plan.id if ts.plan else None,
                        'code': ts.plan.code if ts.plan else None,
                        'display_name': ts.plan.display_name if ts.plan else None,
                        'max_teams': ts.plan.max_teams if ts.plan else None,
                        'max_projects': ts.plan.max_projects if ts.plan else None,
                        'max_team_members_per_team': ts.plan.max_team_members_per_team if ts.plan else None,
                        'max_project_members_per_project': ts.plan.max_project_members_per_project if ts.plan else None,
                        'can_add_users_to_project': ts.plan.can_add_users_to_project if ts.plan else None,
                        'features': ts.plan.features if ts.plan else None,
                    } if ts.plan else None,
                    'price': {
                        'id': ts.price.id if ts.price else None,
                        'key': ts.price.key if ts.price else None,
                        'nickname': ts.price.nickname if ts.price else None,
                        'currency': ts.price.currency if ts.price else None,
                        'amount_cents': ts.price.amount_cents if ts.price else None,
                        'interval': ts.price.interval if ts.price else None,
                        'trial_days': ts.price.trial_days if ts.price else None,
                        'per_seat_amount_cents': ts.price.per_seat_amount_cents if ts.price else None,
                        'per_seat_metric': ts.price.per_seat_metric if ts.price else None,
                    } if ts.price else None,
                })
        except Exception:
            ts_obj = []

        return jsonify({
            'success': True,
            'message': 'Usuário criado com sucesso',
            'user': result.user,
            'token': result.token,
            'team_subscriptions': ts_obj
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@user_bp.route('/users/login', methods=['POST'])
def login_user():
    """Login de usuário"""
    try:
        data = request.json

        if not data.get('email') or not data.get('senha'):
            return jsonify({'error': 'Email e senha são obrigatórios'}), 400

        result = auth_service.login(
            username_or_email=data['email'],
            password=data['senha']
        )

        if result.success:
            # Build team_subscriptions list for this user (if billing owner)
            ts_obj = []
            try:
                subscriptions = TeamSubscription.query.filter_by(
                    billing_user_id=result.user['id'], 
                    is_deleted=False
                ).all()
                
                for ts in subscriptions:
                    ts_obj.append({
                        'id': ts.id,
                        'team_id': ts.team_id,
                        'billing_user_id': ts.billing_user_id,
                        'status': ts.status,
                        'quantity': ts.quantity,
                        'trial_end': ts.trial_end.isoformat() if ts.trial_end else None,
                        'current_period_start': ts.current_period_start.isoformat() if ts.current_period_start else None,
                        'current_period_end': ts.current_period_end.isoformat() if ts.current_period_end else None,
                        'cancel_at_period_end': ts.cancel_at_period_end,
                        'canceled_at': ts.canceled_at.isoformat() if ts.canceled_at else None,
                        'plan': {
                            'id': ts.plan.id if ts.plan else None,
                            'code': ts.plan.code if ts.plan else None,
                            'display_name': ts.plan.display_name if ts.plan else None,
                            'max_teams': ts.plan.max_teams if ts.plan else None,
                            'max_projects': ts.plan.max_projects if ts.plan else None,
                            'max_team_members_per_team': ts.plan.max_team_members_per_team if ts.plan else None,
                            'max_project_members_per_project': ts.plan.max_project_members_per_project if ts.plan else None,
                            'can_add_users_to_project': ts.plan.can_add_users_to_project if ts.plan else None,
                            'features': ts.plan.features if ts.plan else None,
                        } if ts.plan else None,
                        'price': {
                            'id': ts.price.id if ts.price else None,
                            'key': ts.price.key if ts.price else None,
                            'nickname': ts.price.nickname if ts.price else None,
                            'currency': ts.price.currency if ts.price else None,
                            'amount_cents': ts.price.amount_cents if ts.price else None,
                            'interval': ts.price.interval if ts.price else None,
                            'trial_days': ts.price.trial_days if ts.price else None,
                            'per_seat_amount_cents': ts.price.per_seat_amount_cents if ts.price else None,
                            'per_seat_metric': ts.price.per_seat_metric if ts.price else None,
                        } if ts.price else None,
                    })
            except Exception:
                ts_obj = []

            return jsonify({
                'success': True,
                'message': 'Login realizado com sucesso',
                'user': result.user,
                'token': result.token,
                'team_subscriptions': ts_obj
            }), 200
        else:
            return jsonify({'error': result.error}), 401

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# List User is in-active for now
# @user_bp.route('/users', methods=['GET'])
# @auth_service.require_auth
# def get_users():
#     users = User.query.all()
#     return jsonify([user.to_dict() for user in users])


# Create User is in-active for now
# @user_bp.route('/users', methods=['POST'])
# @auth_service.require_auth
# def create_user():
#     data = request.json
#     user = User(username=data['username'], email=data['email'])
#     db.session.add(user)
#     db.session.commit()
#     return jsonify(user.to_dict()), 201


@user_bp.route('/users/<int:user_id>', methods=['GET'])
@auth_service.require_auth
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['PUT'])
@auth_service.require_auth
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    user.first_name = data.get("first_name", user.first_name)
    user.last_name = data.get("last_name", user.last_name)
    user.username = data.get('username', user.username)
    db.session.commit()
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['DELETE'])
@auth_service.require_auth
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return '', 204


@user_bp.route('/users/forget-password', methods=['POST'])
def forget_password():
    data = request.json
    email = data.get('email')
    if not email:
        return jsonify({'error': 'Email é obrigatório'}), 400

    result = auth_service.reset_password_request(email)

    if result.success:
        return jsonify({'success': True, 'message': result.message}), 200
    else:
        return jsonify({'error': result.error}), 400


@user_bp.route('/users/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    token = data.get("token")
    password_text = data.get("senha")

    if not token or not password_text:
        return jsonify(
            {'success': False, 'message': 'Token e senha são obrigatórios'}
        ), 400

    result = auth_service.reset_password(token, password_text)

    if result.success:
        return jsonify({'success': True, 'message': result.message}), 200
    else:
        return jsonify({'error': result.error}), 400


@user_bp.route('/users/change-password', methods=['POST'])
@auth_service.require_auth
def change_user_password():
    data = request.json
    user = g.current_user
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not user or not current_password or not new_password:
        return jsonify(
            {'success': False, 'message': 'Senha atual e nova senha são obrigatórias'}
        ), 400

    result = auth_service.change_password(user.id, current_password, new_password)

    if result.success:
        return jsonify({'success': True, 'message': result.message}), 200
    else:
        return jsonify({'error': result.error}), 400
