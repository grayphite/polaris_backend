#!/usr/bin/env python3
"""
Script de teste para validação do POLARIS Backend
"""

import pytest
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5001"


def test_health_check():
    """Testa o health check básico"""
    response = requests.get(f"{BASE_URL}/api/health")
    assert response.status_code == 200
    assert "status" in response.json()


def test_generate_document_without_auth():
    """Testa endpoint protegido sem autenticação"""
    response = requests.post(
        f"{BASE_URL}/api/generate-document",
        json={"prompt": "Teste"}
    )
    assert response.status_code == 401


@pytest.fixture(scope="module")
def user_token():
    """Cria um usuário e retorna o token JWT para testes"""
    user_data = {
        "nome": "Usuario Teste",
        "email": f"teste_{int(datetime.now().timestamp())}@polaris.com",
        "senha": "123456"
    }
    response = requests.post(
        f"{BASE_URL}/api/users/register",
        json=user_data
    )
    assert response.status_code == 201
    result = response.json()
    return result.get('token')


def test_user_registration(user_token):
    """Testa se o token foi gerado na criação de usuário"""
    assert user_token is not None
    assert isinstance(user_token, str)
    assert len(user_token) > 10


def test_claude_ai_simulation(user_token):
    """Testa o Claude AI em modo simulação"""
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{BASE_URL}/api/ai/chat",
        headers=headers,
        json={"prompt": "Olá, como você pode me ajudar?"}
    )
    assert response.status_code == 200
    result = response.json()
    assert "success" in result or "message" in result
