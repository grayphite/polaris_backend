"""
AuthService - Sistema de Autenticação e Autorização

Este service gerencia autenticação de usuários, geração de tokens JWT,
validação de permissões e controle de sessões.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from functools import wraps
from typing import Dict, Optional, Any

import bcrypt
import jwt
from flask import request, jsonify, g

from src.extensions import db
from src.models import User

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:3000")


@dataclass
class AuthResult:
    """Resultado de operação de autenticação"""
    success: bool
    user: Optional[Dict] = None
    message: Optional[str] = None
    token: Optional[str] = None
    error: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass
class TokenData:
    """Dados extraídos do token JWT"""
    user_id: int
    username: str
    email: str
    expires_at: datetime
    is_valid: bool = True


class AuthService:
    """Service para autenticação e autorização"""

    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
        self.algorithm = 'HS256'
        self.token_expiry_hours = 24
        self.refresh_token_expiry_days = 30
        self.reset_password_expiry_minutes = 30

    def register_user(self, username: str, email: str, password: str,
                      first_name: str = None, last_name: str = None, 
                      role: str = 'owner') -> AuthResult:
        """
        Registrar novo usuário
        
        Args:
            username: Nome de usuário único
            email: Email único
            password: Senha em texto plano
            first_name: Primeiro nome (opcional)
            last_name: Último nome (opcional)
            role: Role do usuário (default: 'member', can be 'member' or 'owner')
            
        Returns:
            AuthResult com resultado da operação
        """
        try:
            # Verificar se usuário já existe
            existing_user = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()

            if existing_user:
                if existing_user.username == username:
                    return AuthResult(
                        success=False,
                        error="Nome de usuário já existe"
                    )
                else:
                    return AuthResult(
                        success=False,
                        error="Email já está em uso"
                    )

            # Validar dados
            validation_error = self._validate_user_data(username, email, password)
            if validation_error:
                return AuthResult(
                    success=False,
                    error=validation_error
                )

            # Validate role
            valid_roles = ['owner', 'member']
            if role not in valid_roles:
                role = 'owner'  # Default to owner if invalid

            # Hash da senha
            password_hash = self._hash_password(password)

            # Criar usuário
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                first_name=first_name or '',
                last_name=last_name or '',
                role=role  # Set role from parameter
            )

            db.session.add(user)
            db.session.commit()

            # Gerar token
            token, expires_at = self._generate_token(user)

            return AuthResult(
                success=True,
                user=user.to_dict(),
                token=token,
                expires_at=expires_at
            )

        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro no registro: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno no registro"
            )

    def login(self, username_or_email: str, password: str) -> AuthResult:
        """
        Fazer login do usuário
        
        Args:
            username_or_email: Username ou email
            password: Senha em texto plano
            
        Returns:
            AuthResult com resultado da autenticação
        """
        try:
            # Buscar usuário por username ou email
            user = User.query.filter(
                (User.username == username_or_email) |
                (User.email == username_or_email)
            ).first()

            if not user:
                return AuthResult(
                    success=False,
                    error="Usuário não encontrado"
                )

            # Verificar senha
            if not self._verify_password(password, user.password_hash):
                return AuthResult(
                    success=False,
                    error="Senha incorreta"
                )

            # Atualizar último login
            user.last_login = datetime.now(UTC)
            db.session.commit()

            # Gerar token
            token, expires_at = self._generate_token(user)

            return AuthResult(
                success=True,
                user=user.to_dict(),
                token=token,
                expires_at=expires_at
            )

        except Exception as e:
            self._log_error(f"Erro no login: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno no login"
            )

    def validate_token(self, token: str) -> TokenData:
        """
        Validar token JWT
        
        Args:
            token: Token JWT
            
        Returns:
            TokenData com dados do token
        """
        try:
            # Decodificar token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Extrair dados
            user_id = payload.get('user_id')
            username = payload.get('username')
            email = payload.get('email')
            exp = payload.get('exp')

            if not all([user_id, username, email, exp]):
                return TokenData(
                    user_id=0,
                    username='',
                    email='',
                    expires_at=datetime.now(UTC),
                    is_valid=False
                )

            expires_at = datetime.fromtimestamp(exp, tz=UTC)

            # Verificar se token não expirou
            if datetime.now(UTC) > expires_at:
                return TokenData(
                    user_id=user_id,
                    username=username,
                    email=email,
                    expires_at=expires_at,
                    is_valid=False
                )

            # Verificar se usuário ainda existe
            user = User.query.get(user_id)
            if not user:
                return TokenData(
                    user_id=user_id,
                    username=username,
                    email=email,
                    expires_at=expires_at,
                    is_valid=False
                )

            return TokenData(
                user_id=user_id,
                username=username,
                email=email,
                expires_at=expires_at,
                is_valid=True
            )

        except jwt.ExpiredSignatureError:
            return TokenData(
                user_id=0,
                username='',
                email='',
                expires_at=datetime.now(UTC),
                is_valid=False
            )
        except jwt.InvalidTokenError:
            return TokenData(
                user_id=0,
                username='',
                email='',
                expires_at=datetime.now(UTC),
                is_valid=False
            )
        except Exception as e:
            self._log_error(f"Erro na validação do token: {str(e)}")
            return TokenData(
                user_id=0,
                username='',
                email='',
                expires_at=datetime.now(UTC),
                is_valid=False
            )

    def refresh_token(self, token: str) -> AuthResult:
        """
        Renovar token JWT
        
        Args:
            token: Token atual
            
        Returns:
            AuthResult com novo token
        """
        try:
            token_data = self.validate_token(token)

            if not token_data.is_valid:
                return AuthResult(
                    success=False,
                    error="Token inválido"
                )

            # Buscar usuário
            user = User.query.get(token_data.user_id)
            if not user:
                return AuthResult(
                    success=False,
                    error="Usuário não encontrado"
                )

            # Gerar novo token
            new_token, expires_at = self._generate_token(user)

            return AuthResult(
                success=True,
                user=user.to_dict(),
                token=new_token,
                expires_at=expires_at
            )

        except Exception as e:
            self._log_error(f"Erro na renovação do token: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno na renovação"
            )

    def change_password(self, user_id: int, current_password: str, new_password: str) -> AuthResult:
        """
        Alterar senha do usuário
        
        Args:
            user_id: ID do usuário
            current_password: Senha atual
            new_password: Nova senha
            
        Returns:
            AuthResult com resultado da operação
        """
        try:
            # Buscar usuário
            user = User.query.get(user_id)
            if not user:
                return AuthResult(
                    success=False,
                    error="Usuário não encontrado"
                )

            # Verificar senha atual
            if not self._verify_password(current_password, user.password_hash):
                return AuthResult(
                    success=False,
                    error="Senha atual incorreta"
                )

            # Validar nova senha
            validation_error = self._validate_password(new_password)
            if validation_error:
                return AuthResult(
                    success=False,
                    error=validation_error
                )

            # Atualizar senha
            user.password_hash = self._hash_password(new_password)
            user.updated_at = datetime.now(UTC)
            db.session.commit()

            return AuthResult(
                success=True,
                user=user.to_dict()
            )

        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro na alteração de senha: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno na alteração de senha"
            )

    def get_user_by_token(self, token: str) -> Optional[User]:
        """
        Obter usuário pelo token
        
        Args:
            token: Token JWT
            
        Returns:
            User ou None se inválido
        """
        try:
            token_data = self.validate_token(token)

            if not token_data.is_valid:
                return None

            return User.query.get(token_data.user_id)

        except Exception as e:
            self._log_error(f"Erro ao obter usuário por token: {str(e)}")
            return None

    def require_auth(self, f):
        """
        Decorator para exigir autenticação em rotas
        
        Usage:
            @auth_service.require_auth
            def protected_route():
                # current_user estará disponível
                pass
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Obter token do header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Token de acesso requerido'}), 401

            try:
                # Extrair token (formato: "Bearer <token>")
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Formato de token inválido'}), 401

            # Validar token
            token_data = self.validate_token(token)
            if not token_data.is_valid:
                return jsonify({'error': 'Token inválido ou expirado'}), 401

            # Buscar usuário
            user = User.query.get(token_data.user_id)
            if not user:
                return jsonify({'error': 'Usuário não encontrado'}), 401

            g.current_user = user

            return f(*args, **kwargs)

        return decorated_function

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de autenticação
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Testar geração e validação de token
            test_user_data = {
                'id': 1,
                'username': 'test',
                'email': 'test@test.com'
            }

            # Gerar token de teste
            test_payload = {
                'user_id': test_user_data['id'],
                'username': test_user_data['username'],
                'email': test_user_data['email'],
                'exp': datetime.now(UTC) + timedelta(minutes=1)
            }

            test_token = jwt.encode(test_payload, self.secret_key, algorithm=self.algorithm)

            # Validar token de teste
            token_data = self.validate_token(test_token)

            return {
                "status": "healthy" if token_data.is_valid else "unhealthy",
                "secret_key_configured": bool(
                    self.secret_key and self.secret_key != 'dev-secret-key-change-in-production'),
                "algorithm": self.algorithm,
                "token_expiry_hours": self.token_expiry_hours,
                "test_token_valid": token_data.is_valid,
                "last_test": datetime.now(UTC).isoformat()
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "secret_key_configured": bool(self.secret_key),
                "algorithm": self.algorithm,
                "error": str(e),
                "last_test": datetime.now(UTC).isoformat()
            }

    def reset_password_request(self, email: str) -> AuthResult:
        """
        Solicitar redefinição de senha (placeholder)

        Args:
            email: Email do usuário

        Returns:
            AuthResult com resultado da operação
        """
        try:
            # Buscar usuário pelo email
            user = User.query.filter_by(email=email).first()
            if not user:
                return AuthResult(
                    success=False,
                    error="Usuário com este email não encontrado"
                )

            # Aqui geraria um token de redefinição e enviaria por email
            # Placeholder - implementar envio de email quando EmailService estiver pronto
            expires_at = datetime.now(UTC) + timedelta(minutes=self.reset_password_expiry_minutes)
            reset_token = self._generate_token(user, expires_at=expires_at)
            reset_link = f"{APP_BASE_URL}/reset-password?token={reset_token[0]}"

            from src.services import email_service

            state = email_service.send_reset_password_email(user_email=email, reset_link=reset_link)
            if not state['success']:
                return AuthResult(
                    success=False,
                    error="Erro ao enviar email de redefinição"
                )
            # Simular envio de email
            self._log_error(f"Redefinição de senha solicitada para {email}. Token: {reset_token}")

            return AuthResult(
                success=True,
                message="Instruções para redefinição de senha enviadas para o email"
            )

        except Exception as e:
            self._log_error(f"Erro na solicitação de redefinição de senha: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno na solicitação de redefinição"
            )

    def reset_password(self, token: str, password: str) -> AuthResult:
        """
        Redefinir senha do usuário
        """
        try:
            user = self.get_user_by_token(token)
            if not user:
                return AuthResult(
                    success=False,
                    error="Usuário não encontrado"
                )

            user.password_hash = self._hash_password(password)
            user.updated_at = datetime.now(UTC)
            db.session.commit()

            return AuthResult(
                success=True,
                message="Senha redefinida com sucesso"
            )

        except Exception as e:
            self._log_error(f"Erro na redefinição de senha: {str(e)}")
            return AuthResult(
                success=False,
                error="Erro interno na redefinição de senha"
            )

    # Métodos privados auxiliares

    def _generate_token(self, user: User, expires_at: datetime = None) -> tuple[str, datetime]:
        """Gerar token JWT para usuário"""
        if not expires_at:
            expires_at = datetime.now(UTC) + timedelta(hours=self.token_expiry_hours)

        payload = {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'exp': int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, expires_at

    def _hash_password(self, password: str) -> str:
        """Hash da senha usando bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verificar senha contra hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    def _validate_user_data(self, username: str, email: str, password: str) -> Optional[str]:
        """Validar dados do usuário"""
        # Validar username
        if not username or len(username) < 3:
            return "Username deve ter pelo menos 3 caracteres"

        if len(username) > 50:
            return "Username deve ter no máximo 50 caracteres"

        # Validar email
        if not email or '@' not in email:
            return "Email inválido"

        if len(email) > 100:
            return "Email deve ter no máximo 100 caracteres"

        # Validar senha
        password_error = self._validate_password(password)
        if password_error:
            return password_error

        return None

    def _validate_password(self, password: str) -> Optional[str]:
        """Validar senha"""
        if not password:
            return "Senha é obrigatória"

        if len(password) < 6:
            return "Senha deve ter pelo menos 6 caracteres"

        if len(password) > 100:
            return "Senha deve ter no máximo 100 caracteres"

        return None

    def _log_error(self, error_msg: str):
        """Log de erro"""
        try:
            # Aqui integraria com LoggingService quando implementado
            print(f"[ERROR] AuthService: {error_msg}")
        except:
            print(f"[ERROR] AuthService: {error_msg}")


# Instância global do service
auth_service = AuthService()


def require_auth(f):
    """
    Decorator para proteger rotas que requerem autenticação
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extrair token do header Authorization
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token de acesso requerido'}), 401

        try:
            token = auth_header.split(' ')[1]
        except IndexError:
            return jsonify({'error': 'Formato de token inválido'}), 401

        # Validar token
        validation_result = auth_service.validate_token(token)
        if not validation_result.is_valid:
            return jsonify({'error': 'Token inválido ou expirado'}), 401

        # Buscar usuário
        user = User.query.get(validation_result.user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 401

        # Adicionar usuário ao Flask g object
        g.current_user = user

        return f(*args, **kwargs)

    return decorated_function
