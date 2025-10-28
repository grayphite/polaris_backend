"""
POLARIS Backend - Sistema de Wealth Planning com IA
App entrypoint refactored for scalability and maintainability
"""

import logging
import os

from dotenv import load_dotenv
from flask import Flask

from src.extensions import db, migrate, cors

# load root level env file
load_dotenv("./.env")

# Import models for migrations
from src.models import *  # noqa: F401

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CORS_ALLOWED_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')


def create_app():
    app = Flask(__name__, static_folder='static')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///polaris.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'polaris-secret-key-dev')

    # Extensions
    migrate.init_app(app, db)
    db.init_app(app)
    cors.init_app(
        app,
        origins=CORS_ALLOWED_ORIGINS,
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    )

    # Import blueprints
    from src.routes.user import user_bp
    from src.routes.project import project_bp
    from src.routes.chat import chat_bp
    from src.routes.team import team_bp
    from src.routes.invitation import invitation_bp
    from src.routes.stripe_payment import bp as stripe_payment_bp
    # from src.routes.openai_chat import openai_chat_bp  # Commented out - using Anthropic instead
    from src.routes.anthropic_chat import anthropic_chat_bp
    from src.routes.file_upload import file_upload_bp
    # Skipping for now as not being used
    # from src.routes.cliente import cliente_bp
    # from src.routes.ai import ai_bp
    # from src.routes.mcp import mcp_bp
    # from src.routes.search import search_bp

    # Register blueprints
    app.register_blueprint(user_bp, url_prefix='/api')
    app.register_blueprint(project_bp, url_prefix='/api')
    app.register_blueprint(chat_bp, url_prefix='/api')
    app.register_blueprint(team_bp, url_prefix='/api')
    app.register_blueprint(invitation_bp, url_prefix='/api')
    app.register_blueprint(stripe_payment_bp, url_prefix='/api')
    # app.register_blueprint(openai_chat_bp, url_prefix='/api')  # Commented out - using Anthropic instead
    app.register_blueprint(anthropic_chat_bp, url_prefix='/api')
    app.register_blueprint(file_upload_bp, url_prefix='/api')
    
    # Register RAG-enhanced AI routes
    from src.routes.enhanced_ai_routes import register_enhanced_ai_routes
    register_enhanced_ai_routes(app)
    
    # Skipping for now as not being used
    # app.register_blueprint(cliente_bp, url_prefix='/api')
    # app.register_blueprint(ai_bp, url_prefix='/api')
    # app.register_blueprint(mcp_bp, url_prefix='/api')
    # app.register_blueprint(search _bp, url_prefix='/api')

    return app


# For running directly
if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
