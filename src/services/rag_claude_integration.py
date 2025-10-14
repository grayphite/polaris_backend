"""
Integração RAG-Claude no App Principal

Script para integrar as novas funcionalidades RAG-Claude ao app.py existente
sem quebrar funcionalidades atuais.
"""

import logging

from flask import Flask

# Import das rotas enhanced
try:
    from src.routes.enhanced_ai_routes import register_enhanced_ai_routes

    ENHANCED_ROUTES_AVAILABLE = True
except ImportError as e:
    ENHANCED_ROUTES_AVAILABLE = False
    print(f"⚠️ Enhanced routes não disponíveis: {e}")

# Import do middleware
try:
    from src.services.rag_claude_middleware import get_rag_claude_middleware

    MIDDLEWARE_AVAILABLE = True
except ImportError as e:
    MIDDLEWARE_AVAILABLE = False
    print(f"⚠️ RAG middleware não disponível: {e}")


def integrate_rag_claude_to_app(app: Flask) -> dict:
    """
    Integra funcionalidades RAG-Claude ao app Flask existente.
    
    Args:
        app: Instância Flask existente
        
    Returns:
        Dict com status da integração
    """
    integration_status = {
        'success': False,
        'enhanced_routes_registered': False,
        'middleware_available': False,
        'rag_enabled': False,
        'cache_enabled': False,
        'errors': [],
        'warnings': []
    }

    try:
        # 1. Registrar rotas enhanced se disponível
        if ENHANCED_ROUTES_AVAILABLE:
            register_enhanced_ai_routes(app)
            integration_status['enhanced_routes_registered'] = True
            print("✅ Enhanced AI routes registradas em /api/v1/enhanced-ai/*")
        else:
            integration_status['warnings'].append(
                "Enhanced routes não disponíveis - routes originais mantidas"
            )

        # 2. Verificar middleware
        if MIDDLEWARE_AVAILABLE:
            middleware = get_rag_claude_middleware()
            middleware_status = middleware.get_status()

            integration_status['middleware_available'] = True
            integration_status['rag_enabled'] = middleware_status.get('rag_enabled', False)
            integration_status['cache_enabled'] = middleware_status.get('cache_enabled', False)

            print(f"✅ Middleware RAG-Claude inicializado")
            print(f"   RAG: {'✅ Ativo' if integration_status['rag_enabled'] else '⚠️ Indisponível'}")
            print(f"   Cache: {'✅ Ativo' if integration_status['cache_enabled'] else '⚠️ Indisponível'}")

        else:
            integration_status['warnings'].append(
                "Middleware RAG-Claude não disponível"
            )

        # 3. Adicionar endpoint de status da integração
        @app.route('/api/v1/integration-status', methods=['GET'])
        def integration_status_endpoint():
            """Endpoint para verificar status da integração RAG-Claude"""

            current_status = integration_status.copy()

            if MIDDLEWARE_AVAILABLE:
                middleware = get_rag_claude_middleware()
                current_status.update(middleware.get_status())

            return current_status

        print("✅ Endpoint de status criado em /api/v1/integration-status")

        # 4. Verificar se integração foi bem-sucedida
        if integration_status['enhanced_routes_registered'] or integration_status['middleware_available']:
            integration_status['success'] = True
            print("🎉 Integração RAG-Claude concluída com sucesso!")
        else:
            integration_status['errors'].append(
                "Nenhum componente RAG-Claude foi integrado"
            )
            print("❌ Falha na integração RAG-Claude")

        return integration_status

    except Exception as e:
        error_msg = f"Erro na integração: {str(e)}"
        integration_status['errors'].append(error_msg)
        print(f"❌ {error_msg}")
        return integration_status


def setup_rag_logging(app: Flask):
    """
    Configura logging específico para RAG-Claude
    
    Args:
        app: Instância Flask
    """
    try:
        # Configurar logger para RAG
        rag_logger = logging.getLogger('rag')
        rag_logger.setLevel(logging.INFO)

        # Handler para arquivo se app em debug
        if app.debug:
            handler = logging.FileHandler('logs/rag.log')
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            rag_logger.addHandler(handler)

        print("✅ Logging RAG configurado")

    except Exception as e:
        print(f"⚠️ Erro ao configurar logging RAG: {e}")


def print_integration_summary():
    """Imprime resumo das funcionalidades integradas"""

    print("\n" + "=" * 60)
    print("📋 RESUMO DA INTEGRAÇÃO RAG-CLAUDE")
    print("=" * 60)

    print("\n🚀 NOVAS FUNCIONALIDADES DISPONÍVEIS:")

    if ENHANCED_ROUTES_AVAILABLE:
        print("\n📡 ENDPOINTS ENHANCED:")
        print("   POST /api/v1/enhanced-ai/chat-smart")
        print("        → Chat inteligente com RAG automático")
        print("   POST /api/v1/enhanced-ai/chat-rag")
        print("        → Chat garantindo uso do RAG")
        print("   POST /api/v1/enhanced-ai/chat-fallback")
        print("        → Chat com fallback robusto")
        print("   GET  /api/v1/enhanced-ai/status")
        print("        → Status do sistema RAG-Claude")
        print("   GET  /api/v1/enhanced-ai/usage-tips")
        print("        → Dicas de uso otimizado")

    if MIDDLEWARE_AVAILABLE:
        middleware = get_rag_claude_middleware()
        status = middleware.get_status()

        print("\n🔧 COMPONENTES ATIVOS:")
        print(f"   Claude AI: ✅ Sempre disponível")
        print(f"   RAG: {'✅ Ativo' if status.get('rag_enabled') else '❌ Instalar requirements_rag.txt'}")
        print(f"   Cache: {'✅ Redis ativo' if status.get('cache_enabled') else '⚠️ Memória apenas'}")

    print("\n📊 STATUS DA INTEGRAÇÃO:")
    print("   GET /api/v1/integration-status")
    print("        → Verificar status completo da integração")

    print("\n💡 COMO USAR:")
    print("   1. Para chat geral: POST /api/v1/enhanced-ai/chat-smart")
    print("   2. Para consultas jurídicas: POST /api/v1/enhanced-ai/chat-rag")
    print("   3. Para sistemas críticos: POST /api/v1/enhanced-ai/chat-fallback")

    if not MIDDLEWARE_AVAILABLE or not get_rag_claude_middleware().rag_enabled:
        print("\n🔧 PARA ATIVAR RAG COMPLETO:")
        print("   pip install -r requirements_rag.txt")
        print("   (Sistema funciona sem RAG usando Claude puro)")

    print("\n✅ COMPATIBILIDADE:")
    print("   • Rotas originais /api/v1/ai/* mantidas intactas")
    print("   • Funcionalidades existentes preservadas")
    print("   • Fallback automático para Claude original")

    print("=" * 60)


def verify_integration_health() -> bool:
    """
    Verifica se a integração está funcionando corretamente
    
    Returns:
        True se integração está saudável
    """
    health_status = True

    print("\n🔍 VERIFICANDO SAÚDE DA INTEGRAÇÃO...")

    # Verificar middleware
    if MIDDLEWARE_AVAILABLE:
        try:
            middleware = get_rag_claude_middleware()
            status = middleware.get_status()

            if status.get('claude_enabled', False):
                print("   ✅ Claude service funcionando")
            else:
                print("   ❌ Claude service com problemas")
                health_status = False

            if status.get('rag_enabled', False):
                print("   ✅ RAG funcionando")
            else:
                print("   ⚠️ RAG não disponível (esperado se requirements_rag.txt não instalado)")

            if status.get('cache_enabled', False):
                print("   ✅ Cache funcionando")
            else:
                print("   ⚠️ Cache limitado (Redis não disponível)")

        except Exception as e:
            print(f"   ❌ Erro no middleware: {e}")
            health_status = False
    else:
        print("   ❌ Middleware não disponível")
        health_status = False

    # Verificar rotas
    if ENHANCED_ROUTES_AVAILABLE:
        print("   ✅ Enhanced routes disponíveis")
    else:
        print("   ⚠️ Enhanced routes não disponíveis")

    status_msg = "✅ INTEGRAÇÃO SAUDÁVEL" if health_status else "⚠️ INTEGRAÇÃO COM PROBLEMAS"
    print(f"\n{status_msg}")

    return health_status


# Função principal para usar no app.py
def initialize_rag_claude_integration(app: Flask, verbose: bool = True) -> dict:
    """
    Função principal para inicializar integração RAG-Claude
    
    Args:
        app: Instância Flask
        verbose: Se deve imprimir logs detalhados
        
    Returns:
        Dict com status da integração
    """
    if verbose:
        print("\n🚀 INICIANDO INTEGRAÇÃO RAG-CLAUDE...")

    # Configurar logging
    setup_rag_logging(app)

    # Integrar componentes
    status = integrate_rag_claude_to_app(app)

    # Verificar saúde
    if verbose:
        verify_integration_health()
        print_integration_summary()

    return status


# Para uso direto no app.py
if __name__ == "__main__":
    print("Este módulo deve ser importado no app.py principal")
    print("Exemplo de uso:")
    print("from src.services.rag_claude_integration import initialize_rag_claude_integration")
    print("initialize_rag_claude_integration(app)")
