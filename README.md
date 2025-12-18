# POLARIS Backend

Sistema de backend completo para POLARIS - Planning Operations & Legal Analysis for Revenue & International Structures.

##  **Visão Geral**

O POLARIS é uma plataforma de inteligência artificial especializada em **wealth planning** (planejamento patrimonial) que automatiza a criação de documentos jurídicos complexos para advogados tributaristas, integrando fontes jurídicas dos Estados Unidos e Brasil através do sistema **MCP (Model Context Protocol)**.

##  **Funcionalidades Principais**

### ** Inteligência Artificial**
- **Claude AI** integrado para assistência especializada
- **RAG (Retrieval-Augmented Generation)** com contexto jurídico
- **Chat inteligente** para wealth planning
- **Geração automática** de documentos profissionais

### ** Sistema MCP (Model Context Protocol)**
- **Web scraping** automatizado de fontes jurídicas
- **Indexação inteligente** com busca semântica
- **Fontes dos EUA**: IRS, SEC, Treasury, FINRA, CFTC
- **Fontes do Brasil**: Receita Federal, CVM, BACEN, CFC, SUSEP
- **Processamento automático** de documentos PDF/DOC/TXT

### **🏗 API REST Completa**
- **CRUD completo** para clientes
- **Gestão de usuários** com autenticação
- **Upload e processamento** de documentos
- **Busca semântica** em base jurídica
- **Health checks** e monitoramento

### ** Containerização Docker**
- **Deploy profissional** com Docker
- **Orquestração** com Docker Compose
- **Scripts de automação** incluídos
- **Backup e rollback** automatizados

## 🏗 **Arquitetura Técnica**

### **Stack Tecnológico**
- **Framework**: Flask (Python 3.11+)
- **Banco de Dados**: PostgreSQL (produção) / SQLite (desenvolvimento)
- **Cache**: Redis para sessões e performance
- **ORM**: SQLAlchemy com relacionamentos otimizados
- **IA**: Claude AI (Anthropic) via API
- **Busca**: TF-IDF + FAISS para busca vetorial
- **Containerização**: Docker + Docker Compose

### **Estrutura do Projeto**
```
polaris_backend/
├── src/
│   ├── models/              # Modelos SQLAlchemy
│   │   ├── __init__.py
│   │   ├── user.py          # Usuários do sistema
│   │   ├── cliente.py       # Clientes (wealth planning)
│   │   ├── template_documento.py    # Templates jurídicos
│   │   ├── documento_gerado.py      # Documentos gerados
│   │   └── documento_upload.py      # Documentos enviados
│   ├── routes/              # Endpoints da API
│   │   ├── user.py          # Rotas de usuários
│   │   ├── cliente.py       # Rotas de clientes
│   │   ├── ai_rag.py        # Rotas de IA com RAG
│   │   ├── mcp.py           # Rotas do sistema MCP
│   │   ├── search.py        # Rotas de busca
│   │   └── legal_scraping.py # Rotas de scraping jurídico
│   ├── services/            # Serviços especializados
│   │   ├── claude_rag_service.py    # Claude AI com RAG
│   │   ├── pdf_processor.py         # Processamento de PDFs
│   │   ├── embedding_service.py     # Embeddings e indexação
│   │   ├── web_scraper.py          # Web scraping geral
│   │   ├── legal_sources_scraper.py # Scraping jurídico
│   │   └── legal_content_processor.py # Processamento jurídico
│   ├── static/              # Frontend integrado
│   └── main.py              # Aplicação principal Flask
├── Dockerfile               # Containerização
├── docker-entrypoint.sh     # Script de inicialização
├── requirements.txt         # Dependências Python
└── README.md               # Esta documentação
```

## � **Modelos de Dados**

### **User (Usuários)**
```python
- id: Integer (PK)
- username: String (único)
- email: String (único)
- password_hash: String
- first_name: String
- last_name: String
- created_at: DateTime
- updated_at: DateTime
```

### **Cliente (Clientes de Wealth Planning)**
```python
- id: Integer (PK)
- user_id: Integer (FK)
- nome: String
- email: String
- telefone: String
- patrimonio_estimado: Decimal
- objetivos_planejamento: Text
- estruturas_existentes: Text
- observacoes: Text
- created_at: DateTime
- updated_at: DateTime
- deleted_at: DateTime (soft delete)
```

### **DocumentoUpload (Documentos Enviados)**
```python
- id: Integer (PK)
- user_id: Integer (FK)
- filename: String
- original_filename: String
- file_path: String
- file_size: Integer
- mime_type: String
- processed: Boolean
- content_extracted: Text
- created_at: DateTime
```

### **TemplateDeDocumento (Templates Jurídicos)**
```python
- id: Integer (PK)
- nome: String
- categoria: String (Trust, Estate, International, Corporate)
- conteudo: Text
- placeholders: JSON
- created_at: DateTime
- updated_at: DateTime
```

### **DocumentoGerado (Documentos Criados)**
```python
- id: Integer (PK)
- user_id: Integer (FK)
- cliente_id: Integer (FK)
- template_id: Integer (FK)
- titulo: String
- conteudo: Text
- status: String
- created_at: DateTime
- updated_at: DateTime
```

## 🔌 **Endpoints da API**

### **🤖 Inteligência Artificial**
```http
POST /api/generate-document     # Gerar documento com Claude AI
POST /api/chat-rag             # Chat com RAG ativo
GET  /api/health               # Health check da IA
```

### ** Gestão de Clientes**
```http
GET    /api/clientes           # Listar clientes (paginação + busca)
GET    /api/clientes/{id}      # Obter cliente específico
POST   /api/clientes           # Criar novo cliente
PUT    /api/clientes/{id}      # Atualizar cliente
DELETE /api/clientes/{id}      # Excluir cliente (soft delete)
POST   /api/clientes/{id}/restore  # Restaurar cliente
GET    /api/clientes/stats     # Estatísticas dos clientes
```

### ** Sistema MCP**
```http
POST /api/mcp/upload           # Upload de documentos
GET  /api/mcp/documents        # Listar documentos processados
POST /api/mcp/process          # Processar documento específico
DELETE /api/mcp/documents/{id} # Excluir documento
```

### ** Busca e Indexação**
```http
POST /api/search/index         # Indexar documento
POST /api/search/query         # Busca semântica
GET  /api/search/stats         # Estatísticas do índice
DELETE /api/search/index       # Limpar índice
```

### **⚖ Fontes Jurídicas**
```http
POST /api/legal/scrape         # Executar scraping
GET  /api/legal/sources        # Listar fontes disponíveis
GET  /api/legal/data           # Obter dados coletados
POST /api/legal/process        # Processar dados jurídicos
```

### ** Sistema**
```http
GET /api/health                # Health check geral
GET /api/status                # Status detalhado do sistema
```

##  **Configuração e Deploy**

### ** Deploy com Docker (Recomendado)**

#### **1. Pré-requisitos**
```bash
# Docker e Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

#### **2. Clone e Configure**
```bash
git clone https://github.com/carlossilvatbh/polaris_backend.git
cd polaris_backend

# Configure variáveis de ambiente
cp .env.example .env
nano .env  # Configure suas chaves API
```

#### **3. Deploy Completo**
```bash
# Build da imagem
docker build -t polaris-backend .

# Executar com Docker Compose (recomendado)
# Baixe o docker-compose.yml do repositório polaris_docker
docker-compose up -d
```

### **🔧 Deploy Manual (Desenvolvimento)**

#### **1. Instalação**
```bash
git clone https://github.com/carlossilvatbh/polaris_backend.git
cd polaris_backend

# Ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate  # Windows

# Dependências
pip install -r requirements.txt
```

#### **2. Configuração**
```bash
# Variáveis de ambiente
export ANTHROPIC_API_KEY="sk-ant-api03-sua-chave-aqui"
export DATABASE_URL="postgresql://user:pass@localhost/polaris"
export SECRET_KEY="sua-chave-secreta-32-chars-minimo"
```

#### **3. Execução**
```bash
python src/main.py
```

## 🚀 Setup Rápido

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente
Crie um arquivo `.env` na raiz do projeto com:
```
DATABASE_URL=sqlite:///polaris.db  # Ou sua URL do PostgreSQL
SECRET_KEY=uma-chave-secreta
PORT=5000
```

### 3. Inicializar banco de dados e migrações
```bash
flask db init           # Executar apenas uma vez
flask db migrate -m "Initial migration"
flask db upgrade
```

### 4. Rodar o servidor
```bash
python src/main.py
```

## 🛠️ Migrations e Banco de Dados
- Use Flask-Migrate para gerenciar alterações no banco de dados.
- Comandos principais:
  - `flask db migrate -m "mensagem"` — cria uma nova migração
  - `flask db upgrade` — aplica migrações
  - `flask db downgrade` — desfaz migrações

## 🔥 Application Factory & Blueprints
- O app usa o padrão `create_app()` para escalabilidade.
- Rotas são organizadas em Blueprints para modularidade.
- Extensões (CORS, SQLAlchemy, Migrate) são inicializadas no factory.

## 🧑‍💻 Testes
- Testes estão em `tests/`.
- Execute com:
```bash
pytest
```

##  **Variáveis de Ambiente**

### **Obrigatórias**
```bash
# Claude AI (OBRIGATÓRIO)
ANTHROPIC_API_KEY=sk-ant-api03-sua-chave-aqui

# Flask (OBRIGATÓRIO em produção)
SECRET_KEY=sua-chave-secreta-32-chars-minimo
```

### **Opcionais**
```bash
# Banco de dados (padrão: SQLite)
DATABASE_URL=postgresql://user:password@localhost/polaris

# Cache Redis (padrão: sem cache)
REDIS_URL=redis://localhost:6379/0

# CORS (padrão: todas as origens)
CORS_ORIGINS=https://seudominio.com,https://www.seudominio.com

# Log level (padrão: INFO)
LOG_LEVEL=DEBUG

# Porta (padrão: 5000)
PORT=5000
```

## **Monitoramento e Health Checks**

### **Health Check Endpoint**
```bash
curl http://localhost:5000/api/health
```

**Resposta de Sucesso:**
```json
{
  "status": "healthy",
  "timestamp": "2024-09-14T17:30:00Z",
  "services": {
    "database": "connected",
    "claude_ai": "operational",
    "redis": "connected",
    "mcp_system": "active"
  },
  "version": "1.0.0"
}
```

### **Status Detalhado**
```bash
curl http://localhost:5000/api/status
```

## **Sistema MCP em Detalhes**

### **Fontes Jurídicas Integradas**

#### **Estados Unidos:**
- **IRS (Internal Revenue Service)**
  - Tax code regulations
  - International business guidance
  - Large Business & International compliance
- **SEC (Securities and Exchange Commission)**
- **Treasury Department**
- **FINRA (Financial Industry Regulatory Authority)**
- **CFTC (Commodity Futures Trading Commission)**

#### **Brasil:**
- **Receita Federal do Brasil**
  - Acordos internacionais
  - Orientações tributárias
  - Acordos de cooperação
- **CVM (Comissão de Valores Mobiliários)**
- **BACEN (Banco Central do Brasil)**
- **CFC (Conselho Federal de Contabilidade)**
- **SUSEP (Superintendência de Seguros Privados)**

### **Processamento Inteligente**
- **Categorização automática** por área jurídica
- **Extração de conceitos-chave** relevantes
- **Scores de relevância** para wealth planning
- **Indexação vetorial** para busca semântica

## **Integração Claude AI**

### **Funcionalidades**
- **Chat especializado** em wealth planning
- **RAG ativo** com contexto jurídico
- **Geração de documentos** profissionais
- **Análise de estruturas** offshore
- **Recomendações personalizadas** por jurisdição

### **Exemplo de Uso**
```python
# Chat com RAG
response = claude_rag_service.chat_with_context(
    prompt="Estrutura de trust para cliente brasileiro com $15M",
    context_type="wealth_planning",
    user_id=1
)
```

## **Segurança**

### **Implementações de Segurança**
- **CORS configurável** por domínio
- **Validação de entrada** em todos endpoints
- **Soft delete** para preservar dados
- **Isolamento por usuário** (user_id obrigatório)
- **Hash de senhas** com Werkzeug
- **Chaves API** via variáveis de ambiente

### **Headers de Segurança**
```python
# Configurados automaticamente
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
```

## **Performance**

### **Otimizações Implementadas**
- **Cache Redis** para sessões e queries frequentes
- **Índices de banco** otimizados
- **Lazy loading** de relacionamentos
- **Paginação** em todas as listagens
- **Compressão gzip** habilitada
- **Pool de conexões** PostgreSQL

### **Métricas Típicas**
- **Tempo de resposta**: < 200ms (endpoints simples)
- **Chat com IA**: 3-5 segundos
- **Upload de documentos**: < 1 segundo/MB
- **Busca semântica**: < 500ms

## **Desenvolvimento e Testes**

### **Ambiente de Desenvolvimento**
```bash
# Modo debug
export FLASK_ENV=development
export LOG_LEVEL=DEBUG

# Executar
python src/main.py
```

### **Estrutura de Testes**
```bash
# Executar testes (quando implementados)
pytest tests/
```

### **Linting e Formatação**
```bash
# Black (formatação)
black src/

# Flake8 (linting)
flake8 src/
```

## **Backup e Recuperação**

### **Dados Importantes**
- **Banco PostgreSQL** - Dados estruturados
- **Uploads** - Documentos enviados
- **Índices** - Busca semântica
- **Logs** - Auditoria e debugging

### **Backup Automático**
```bash
# Com Docker Compose
docker-compose exec postgres pg_dump -U polaris polaris > backup.sql

# Restauração
docker-compose exec postgres psql -U polaris polaris < backup.sql
```

## **Documentação da API**

### **Formato de Resposta Padrão**
```json
{
  "success": true,
  "data": {},
  "message": "Operação realizada com sucesso",
  "timestamp": "2024-09-14T17:30:00Z"
}
```

### **Códigos de Status HTTP**
- `200` - Sucesso
- `201` - Criado com sucesso
- `400` - Erro de validação
- `401` - Não autorizado
- `404` - Não encontrado
- `409` - Conflito (ex: email duplicado)
- `500` - Erro interno do servidor

### **Paginação**
```http
GET /api/clientes?page=1&per_page=10&search=termo&sort=created_at&order=desc
```

## � **Roadmap**

### **Próximas Funcionalidades**
- [ ] **Autenticação JWT** completa
- [ ] **WebSockets** para chat em tempo real
- [ ] **Notificações** push
- [ ] **Audit trail** completo
- [ ] **API rate limiting**
- [ ] **Testes automatizados** (pytest)
- [ ] **CI/CD pipeline** (GitHub Actions)
- [ ] **Documentação OpenAPI** (Swagger)

### **Melhorias Planejadas**
- [ ] **Cache inteligente** para IA
- [ ] **Processamento assíncrono** de documentos
- [ ] **Métricas avançadas** (Prometheus)
- [ ] **Logs estruturados** (JSON)
- [ ] **Backup automático** agendado

## **Contribuição**

### **Desenvolvimento Local**
```bash
# Fork do repositório
git clone https://github.com/seu-usuario/polaris_backend.git
cd polaris_backend

# Configurar ambiente
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Fazer alterações
# Testar localmente
# Commit e push
```

---

**POLARIS Backend** - Sistema de Wealth Planning com IA  
Versão: 1.0.0 (Containerizada)  
Última atualização: 2024-09-14
