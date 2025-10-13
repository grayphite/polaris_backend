"""
POLARIS Backend - Sistema de Wealth Planning com IA
Aplicação Flask principal
"""

import logging
import os
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv("./.env")

from src.database import db

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Flask
app = Flask(__name__, static_folder='static')

# Configuração CORS
CORS(app, origins=['*'], methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# Configuração do banco de dados
database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///polaris.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'polaris-secret-key-dev')

# Importar modelos
from src.models.user import User
from src.models.cliente import Cliente
from src.models.documento_gerado import DocumentoGerado
from src.models.template_documento import TemplateDeDocumento

# Importar blueprints
from src.routes.user import user_bp
from src.routes.cliente import cliente_bp
from src.routes.ai import ai_bp
from src.routes.mcp import mcp_bp
from src.routes.search import search_bp

# Tentar importar rotas enhanced (RAG)
try:
    from src.services.rag_claude_integration import register_enhanced_ai_routes

    enhanced_routes_available = True
    logger.info("Enhanced AI routes (RAG) disponíveis")
except ImportError:
    enhanced_routes_available = False
    logger.info("Enhanced AI routes (RAG) não disponíveis - "
                "dependências opcionais não instaladas")

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(cliente_bp, url_prefix='/api')
app.register_blueprint(ai_bp, url_prefix='/api')
app.register_blueprint(mcp_bp, url_prefix='/api')
app.register_blueprint(search_bp, url_prefix='/api')

# Registrar rotas enhanced se disponíveis
if enhanced_routes_available:
    try:
        register_enhanced_ai_routes(app)
        logger.info("Enhanced AI routes registradas com sucesso")
    except Exception as e:
        logger.warning(f"Erro ao registrar enhanced AI routes: {str(e)}")


# Rota para servir frontend
@app.route('/')
def serve_frontend():
    """Serve o frontend React"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve arquivos estáticos do frontend"""
    try:
        return send_from_directory(app.static_folder, path)
    except:
        return send_from_directory(app.static_folder, 'index.html')


# Health check
@app.route('/api/health')
def health_check():
    """Health check da aplicação"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'service': 'POLARIS Backend'
    })


# Endpoint básico para chat (placeholder)
@app.route('/api/generate-document', methods=['POST'])
def generate_document():
    """Endpoint placeholder para geração de documentos"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '')

        # Resposta simulada para demonstração
        response = {
            'success': True,
            'response': f'Esta é uma resposta simulada para: {prompt}. Para ativar o Claude AI, configure a variável ANTHROPIC_API_KEY.',
            'model': 'placeholder'
        }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Erro no generate_document: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Criar tabelas
with app.app_context():
    try:
        db.init_app(app)
        db.create_all()
        logger.info("Tabelas do banco de dados criadas com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
