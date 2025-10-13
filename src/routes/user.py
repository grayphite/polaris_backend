from flask import Blueprint, jsonify, request

from src.models.user import User
from src.services.auth_service import auth_service
from src.database import db

user_bp = Blueprint('user', __name__)


@user_bp.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])


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

        result = auth_service.register_user(
            username=data['email'],  # Usar email como username
            email=data['email'],
            password=data['senha'],
            first_name=first_name,
            last_name=last_name
        )

        if result.success:
            return jsonify({
                'success': True,
                'message': 'Usuário criado com sucesso',
                'user': result.user,
                'token': result.token
            }), 201
        else:
            return jsonify({'error': result.error}), 400

    except Exception as e:
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
            return jsonify({
                'success': True,
                'message': 'Login realizado com sucesso',
                'user': result.user,
                'token': result.token
            }), 200
        else:
            return jsonify({'error': result.error}), 401

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@user_bp.route('/users', methods=['POST'])
def create_user():
    data = request.json
    user = User(username=data['username'], email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@user_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    user.first_name = data.get("first_name", user.first_name)
    user.last_name = data.get("last_name", user.last_name)
    user.username = data.get('username', user.username)
    user.email = data.get('email', user.email)
    db.session.commit()
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['DELETE'])
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
    user = request.current_user
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
