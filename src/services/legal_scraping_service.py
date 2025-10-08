"""
LegalScrapingService - Web Scraping de Fontes Jurídicas

Este service gerencia o web scraping automatizado de fontes jurídicas
dos Estados Unidos e Brasil para alimentar o sistema MCP.
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import hashlib

# Imports para web scraping
try:
    from bs4 import BeautifulSoup
    import selenium
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    BeautifulSoup = None
    selenium = None
    webdriver = None

from src.database import db
from src.models import LegalSource, ScrapedContent


@dataclass
class ScrapingResult:
    """Resultado do scraping"""
    success: bool
    source_name: str
    documents_found: int = 0
    documents_processed: int = 0
    error: Optional[str] = None
    execution_time: float = 0.0
    last_update: datetime = None


@dataclass
class LegalDocument:
    """Documento jurídico coletado"""
    title: str
    content: str
    url: str
    source: str
    category: str
    publication_date: Optional[datetime] = None
    document_type: str = "regulation"
    metadata: Dict = None


class LegalScrapingService:
    """Service para web scraping de fontes jurídicas"""
    
    def __init__(self):
        self.data_dir = os.path.join(os.getcwd(), 'legal_data')
        self.cache_dir = os.path.join(self.data_dir, 'cache')
        
        # Criar diretórios
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Configurações
        self.request_delay = 2  # segundos entre requests
        self.timeout = 30
        self.max_retries = 3
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        
        # Fontes jurídicas configuradas
        self.legal_sources = {
            # Estados Unidos
            'irs': {
                'name': 'Internal Revenue Service',
                'country': 'US',
                'base_url': 'https://www.irs.gov',
                'endpoints': [
                    '/businesses/international-businesses',
                    '/individuals/international-taxpayers',
                    '/tax-professionals/international-tax'
                ],
                'selectors': {
                    'content': '.field--name-body, .content-area',
                    'title': 'h1, .page-title',
                    'links': 'a[href*="/pub/"], a[href*="/forms/"]'
                }
            },
            'sec': {
                'name': 'Securities and Exchange Commission',
                'country': 'US',
                'base_url': 'https://www.sec.gov',
                'endpoints': [
                    '/investment/investment-adviser-regulation',
                    '/rules/final',
                    '/divisions/investment/guidance'
                ],
                'selectors': {
                    'content': '.article-content, .field--name-body',
                    'title': 'h1, .page-title',
                    'links': 'a[href*="/rules/"], a[href*="/releases/"]'
                }
            },
            'treasury': {
                'name': 'US Department of Treasury',
                'country': 'US',
                'base_url': 'https://home.treasury.gov',
                'endpoints': [
                    '/policy-issues/international',
                    '/policy-issues/tax-policy',
                    '/resource-center/tax-policy'
                ],
                'selectors': {
                    'content': '.field--name-body, .content',
                    'title': 'h1, .page-title',
                    'links': 'a[href*="/resource-center/"]'
                }
            },
            
            # Brasil
            'receita_federal': {
                'name': 'Receita Federal do Brasil',
                'country': 'BR',
                'base_url': 'https://www.gov.br/receitafederal',
                'endpoints': [
                    '/pt-br/assuntos/orientacao-tributaria/acordos-internacionais',
                    '/pt-br/assuntos/orientacao-tributaria/legislacao',
                    '/pt-br/assuntos/orientacao-tributaria/regimes-aduaneiros-especiais'
                ],
                'selectors': {
                    'content': '.rich-text, .content-core',
                    'title': 'h1, .documentFirstHeading',
                    'links': 'a[href*="/legislacao/"], a[href*="/acordos/"]'
                }
            },
            'cvm': {
                'name': 'Comissão de Valores Mobiliários',
                'country': 'BR',
                'base_url': 'https://www.gov.br/cvm',
                'endpoints': [
                    '/pt-br/assuntos/regulacao',
                    '/pt-br/assuntos/orientacoes',
                    '/pt-br/assuntos/normas'
                ],
                'selectors': {
                    'content': '.rich-text, .content-core',
                    'title': 'h1, .documentFirstHeading',
                    'links': 'a[href*="/normas/"], a[href*="/regulacao/"]'
                }
            },
            'bacen': {
                'name': 'Banco Central do Brasil',
                'country': 'BR',
                'base_url': 'https://www.bcb.gov.br',
                'endpoints': [
                    '/estabilidadefinanceira/regulacao',
                    '/acessoinformacao/legis',
                    '/pre/normativos'
                ],
                'selectors': {
                    'content': '.conteudo, .content',
                    'title': 'h1, .titulo',
                    'links': 'a[href*="/normativos/"], a[href*="/legis/"]'
                }
            }
        }
        
        # Categorias de documentos
        self.document_categories = {
            'tax_treaties': ['treaty', 'acordo', 'tratado', 'convention'],
            'regulations': ['regulation', 'regulamento', 'norma', 'instrução'],
            'guidance': ['guidance', 'orientação', 'circular', 'parecer'],
            'forms': ['form', 'formulário', 'declaração'],
            'rulings': ['ruling', 'decisão', 'acórdão', 'jurisprudência']
        }
    
    def scrape_all_sources(self, force_update: bool = False) -> List[ScrapingResult]:
        """
        Executar scraping de todas as fontes configuradas
        
        Args:
            force_update: Forçar atualização mesmo se cache válido
            
        Returns:
            Lista de resultados do scraping
        """
        results = []
        
        for source_key, source_config in self.legal_sources.items():
            try:
                result = self.scrape_source(source_key, force_update)
                results.append(result)
                
                # Delay entre fontes
                time.sleep(self.request_delay)
                
            except Exception as e:
                results.append(ScrapingResult(
                    success=False,
                    source_name=source_config['name'],
                    error=f"Erro no scraping: {str(e)}"
                ))
        
        return results
    
    def scrape_source(self, source_key: str, force_update: bool = False) -> ScrapingResult:
        """
        Executar scraping de uma fonte específica
        
        Args:
            source_key: Chave da fonte (irs, sec, receita_federal, etc.)
            force_update: Forçar atualização
            
        Returns:
            ScrapingResult com resultado do scraping
        """
        start_time = time.time()
        
        try:
            if source_key not in self.legal_sources:
                return ScrapingResult(
                    success=False,
                    source_name=source_key,
                    error="Fonte não configurada"
                )
            
            source_config = self.legal_sources[source_key]
            
            # Verificar se precisa atualizar
            if not force_update and self._is_cache_valid(source_key):
                cached_result = self._load_cached_result(source_key)
                if cached_result:
                    return cached_result
            
            # Executar scraping
            documents = []
            
            for endpoint in source_config['endpoints']:
                try:
                    url = urljoin(source_config['base_url'], endpoint)
                    endpoint_docs = self._scrape_endpoint(url, source_config, source_key)
                    documents.extend(endpoint_docs)
                    
                    # Delay entre endpoints
                    time.sleep(self.request_delay)
                    
                except Exception as e:
                    self._log_error(f"Erro no endpoint {endpoint}: {str(e)}")
                    continue
            
            # Processar documentos coletados
            processed_count = 0
            for doc in documents:
                if self._save_document(doc, source_key):
                    processed_count += 1
            
            execution_time = time.time() - start_time
            
            result = ScrapingResult(
                success=True,
                source_name=source_config['name'],
                documents_found=len(documents),
                documents_processed=processed_count,
                execution_time=execution_time,
                last_update=datetime.utcnow()
            )
            
            # Salvar resultado em cache
            self._save_cached_result(source_key, result)
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            return ScrapingResult(
                success=False,
                source_name=self.legal_sources.get(source_key, {}).get('name', source_key),
                error=str(e),
                execution_time=execution_time
            )
    
    def get_scraped_documents(self,
                             source: str = None,
                             category: str = None,
                             country: str = None,
                             limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obter documentos coletados
        
        Args:
            source: Filtrar por fonte
            category: Filtrar por categoria
            country: Filtrar por país (US, BR)
            limit: Limite de resultados
            
        Returns:
            Lista de documentos
        """
        try:
            query = ScrapedContent.query
            
            if source:
                query = query.filter_by(source=source)
            
            if category:
                query = query.filter_by(category=category)
            
            if country:
                # Filtrar por país baseado na fonte
                country_sources = [
                    key for key, config in self.legal_sources.items()
                    if config.get('country') == country
                ]
                if country_sources:
                    query = query.filter(ScrapedContent.source.in_(country_sources))
            
            documents = query.order_by(
                ScrapedContent.created_at.desc()
            ).limit(limit).all()
            
            return [doc.to_dict() for doc in documents]
            
        except Exception as e:
            self._log_error(f"Erro ao obter documentos: {str(e)}")
            return []
    
    def search_documents(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Buscar documentos por texto
        
        Args:
            query: Texto de busca
            limit: Limite de resultados
            
        Returns:
            Lista de documentos encontrados
        """
        try:
            # Busca simples por título e conteúdo
            search_filter = db.or_(
                ScrapedContent.title.ilike(f'%{query}%'),
                ScrapedContent.content.ilike(f'%{query}%')
            )
            
            documents = ScrapedContent.query.filter(
                search_filter
            ).order_by(
                ScrapedContent.created_at.desc()
            ).limit(limit).all()
            
            return [doc.to_dict() for doc in documents]
            
        except Exception as e:
            self._log_error(f"Erro na busca: {str(e)}")
            return []
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """
        Obter estatísticas do scraping
        
        Returns:
            Dict com estatísticas
        """
        try:
            # Estatísticas gerais
            total_docs = ScrapedContent.query.count()
            
            # Por fonte
            source_stats = db.session.query(
                ScrapedContent.source,
                db.func.count(ScrapedContent.id).label('count')
            ).group_by(ScrapedContent.source).all()
            
            # Por categoria
            category_stats = db.session.query(
                ScrapedContent.category,
                db.func.count(ScrapedContent.id).label('count')
            ).group_by(ScrapedContent.category).all()
            
            # Por país
            country_stats = {}
            for source_key, source_config in self.legal_sources.items():
                country = source_config.get('country', 'Unknown')
                if country not in country_stats:
                    country_stats[country] = 0
                
                source_count = ScrapedContent.query.filter_by(source=source_key).count()
                country_stats[country] += source_count
            
            # Última atualização
            last_update = db.session.query(
                db.func.max(ScrapedContent.created_at)
            ).scalar()
            
            # Documentos por data
            today = datetime.utcnow().date()
            docs_today = ScrapedContent.query.filter(
                db.func.date(ScrapedContent.created_at) == today
            ).count()
            
            week_ago = today - timedelta(days=7)
            docs_week = ScrapedContent.query.filter(
                db.func.date(ScrapedContent.created_at) >= week_ago
            ).count()
            
            return {
                'total_documents': total_docs,
                'documents_today': docs_today,
                'documents_this_week': docs_week,
                'by_source': {source: count for source, count in source_stats},
                'by_category': {category: count for category, count in category_stats},
                'by_country': country_stats,
                'configured_sources': len(self.legal_sources),
                'last_update': last_update.isoformat() if last_update else None
            }
            
        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}")
            return {
                'total_documents': 0,
                'documents_today': 0,
                'documents_this_week': 0,
                'by_source': {},
                'by_category': {},
                'by_country': {},
                'configured_sources': 0,
                'last_update': None
            }
    
    def update_source_config(self, source_key: str, config: Dict[str, Any]) -> bool:
        """
        Atualizar configuração de uma fonte
        
        Args:
            source_key: Chave da fonte
            config: Nova configuração
            
        Returns:
            True se atualizado com sucesso
        """
        try:
            if source_key in self.legal_sources:
                self.legal_sources[source_key].update(config)
                return True
            return False
            
        except Exception as e:
            self._log_error(f"Erro na atualização de config: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de scraping
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Verificar bibliotecas
            libraries_available = {
                'requests': True,  # Sempre disponível
                'beautifulsoup4': BeautifulSoup is not None,
                'selenium': selenium is not None
            }
            
            # Testar conectividade com algumas fontes
            connectivity_test = {}
            test_sources = ['irs', 'receita_federal']
            
            for source_key in test_sources:
                if source_key in self.legal_sources:
                    try:
                        base_url = self.legal_sources[source_key]['base_url']
                        response = requests.head(base_url, timeout=10)
                        connectivity_test[source_key] = response.status_code == 200
                    except:
                        connectivity_test[source_key] = False
            
            # Verificar cache
            cache_status = {
                'directory_exists': os.path.exists(self.cache_dir),
                'directory_writable': os.access(self.cache_dir, os.W_OK) if os.path.exists(self.cache_dir) else False
            }
            
            # Estatísticas recentes
            stats = self.get_scraping_stats()
            
            # Determinar status geral
            status = "healthy"
            if not cache_status['directory_writable']:
                status = "degraded"
            elif not any(connectivity_test.values()):
                status = "warning"
            elif not libraries_available['beautifulsoup4']:
                status = "degraded"
            
            return {
                "status": status,
                "libraries": libraries_available,
                "connectivity": connectivity_test,
                "cache": cache_status,
                "sources": {
                    "configured": len(self.legal_sources),
                    "available": list(self.legal_sources.keys())
                },
                "statistics": {
                    "total_documents": stats['total_documents'],
                    "documents_today": stats['documents_today'],
                    "last_update": stats['last_update']
                },
                "config": {
                    "request_delay": self.request_delay,
                    "timeout": self.timeout,
                    "max_retries": self.max_retries
                },
                "last_check": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    # Métodos privados auxiliares
    
    def _scrape_endpoint(self, url: str, source_config: Dict, source_key: str) -> List[LegalDocument]:
        """Fazer scraping de um endpoint específico"""
        documents = []
        
        try:
            # Fazer request
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            if BeautifulSoup is None:
                # Fallback sem BeautifulSoup
                return self._extract_simple_content(response.text, url, source_config, source_key)
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extrair conteúdo principal
            main_content = self._extract_main_content(soup, source_config, url, source_key)
            if main_content:
                documents.append(main_content)
            
            # Buscar links para documentos adicionais
            links = self._extract_document_links(soup, source_config, url)
            
            # Processar alguns links (limitado para evitar sobrecarga)
            for link_url in links[:5]:  # Máximo 5 links por endpoint
                try:
                    link_doc = self._scrape_document_link(link_url, source_config, source_key)
                    if link_doc:
                        documents.append(link_doc)
                    
                    time.sleep(self.request_delay)
                    
                except Exception as e:
                    self._log_error(f"Erro no link {link_url}: {str(e)}")
                    continue
            
            return documents
            
        except Exception as e:
            self._log_error(f"Erro no endpoint {url}: {str(e)}")
            return []
    
    def _extract_main_content(self, soup, source_config: Dict, url: str, source_key: str) -> Optional[LegalDocument]:
        """Extrair conteúdo principal da página"""
        try:
            # Extrair título
            title_selectors = source_config['selectors']['title'].split(', ')
            title = ""
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break
            
            if not title:
                title = "Untitled Document"
            
            # Extrair conteúdo
            content_selectors = source_config['selectors']['content'].split(', ')
            content = ""
            
            for selector in content_selectors:
                content_elems = soup.select(selector)
                if content_elems:
                    content = ' '.join([elem.get_text(strip=True) for elem in content_elems])
                    break
            
            if not content or len(content) < 100:
                return None
            
            # Determinar categoria
            category = self._categorize_document(title, content)
            
            return LegalDocument(
                title=title,
                content=content[:5000],  # Limitar tamanho
                url=url,
                source=source_key,
                category=category,
                publication_date=datetime.utcnow(),
                metadata={
                    'source_name': source_config['name'],
                    'country': source_config.get('country', 'Unknown'),
                    'content_length': len(content)
                }
            )
            
        except Exception as e:
            self._log_error(f"Erro na extração de conteúdo: {str(e)}")
            return None
    
    def _extract_document_links(self, soup, source_config: Dict, base_url: str) -> List[str]:
        """Extrair links para documentos"""
        links = []
        
        try:
            link_selectors = source_config['selectors'].get('links', '')
            if not link_selectors:
                return links
            
            for selector in link_selectors.split(', '):
                link_elems = soup.select(selector)
                
                for elem in link_elems:
                    href = elem.get('href')
                    if href:
                        # Converter para URL absoluta
                        if href.startswith('/'):
                            full_url = urljoin(base_url, href)
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue
                        
                        if full_url not in links:
                            links.append(full_url)
            
            return links[:10]  # Limitar número de links
            
        except Exception as e:
            self._log_error(f"Erro na extração de links: {str(e)}")
            return []
    
    def _scrape_document_link(self, url: str, source_config: Dict, source_key: str) -> Optional[LegalDocument]:
        """Fazer scraping de um link específico"""
        try:
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            if BeautifulSoup is None:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            return self._extract_main_content(soup, source_config, url, source_key)
            
        except Exception as e:
            self._log_error(f"Erro no link {url}: {str(e)}")
            return None
    
    def _extract_simple_content(self, html_content: str, url: str, source_config: Dict, source_key: str) -> List[LegalDocument]:
        """Extração simples sem BeautifulSoup"""
        try:
            # Extração muito básica usando regex
            import re
            
            # Tentar extrair título
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
            title = title_match.group(1) if title_match else "Document"
            
            # Remover tags HTML básicas
            content = re.sub(r'<[^>]+>', ' ', html_content)
            content = ' '.join(content.split())  # Normalizar espaços
            
            if len(content) < 100:
                return []
            
            category = self._categorize_document(title, content)
            
            doc = LegalDocument(
                title=title,
                content=content[:3000],  # Limitar tamanho
                url=url,
                source=source_key,
                category=category,
                publication_date=datetime.utcnow(),
                metadata={
                    'source_name': source_config['name'],
                    'country': source_config.get('country', 'Unknown'),
                    'extraction_method': 'simple'
                }
            )
            
            return [doc]
            
        except Exception as e:
            self._log_error(f"Erro na extração simples: {str(e)}")
            return []
    
    def _categorize_document(self, title: str, content: str) -> str:
        """Categorizar documento baseado no conteúdo"""
        title_lower = title.lower()
        content_lower = content.lower()
        
        for category, keywords in self.document_categories.items():
            for keyword in keywords:
                if keyword in title_lower or keyword in content_lower:
                    return category
        
        return 'general'
    
    def _save_document(self, document: LegalDocument, source_key: str) -> bool:
        """Salvar documento no banco de dados"""
        try:
            # Verificar se documento já existe (por URL)
            existing = ScrapedContent.query.filter_by(url=document.url).first()
            
            if existing:
                # Atualizar se conteúdo mudou
                content_hash = hashlib.md5(document.content.encode('utf-8')).hexdigest()
                if existing.content_hash != content_hash:
                    existing.title = document.title
                    existing.content = document.content
                    existing.content_hash = content_hash
                    existing.category = document.category
                    existing.metadata = document.metadata
                    existing.updated_at = datetime.utcnow()
                    db.session.commit()
                return True
            
            # Criar novo documento
            content_hash = hashlib.md5(document.content.encode('utf-8')).hexdigest()
            
            scraped_content = ScrapedContent(
                title=document.title,
                content=document.content,
                content_hash=content_hash,
                url=document.url,
                source=document.source,
                category=document.category,
                document_type=document.document_type,
                publication_date=document.publication_date,
                metadata=document.metadata or {}
            )
            
            db.session.add(scraped_content)
            db.session.commit()
            
            return True
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro ao salvar documento: {str(e)}")
            return False
    
    def _is_cache_valid(self, source_key: str, max_age_hours: int = 24) -> bool:
        """Verificar se cache é válido"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{source_key}_result.json")
            
            if not os.path.exists(cache_file):
                return False
            
            # Verificar idade do arquivo
            file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
            max_age = timedelta(hours=max_age_hours)
            
            return datetime.utcnow() - file_time < max_age
            
        except Exception as e:
            self._log_error(f"Erro na verificação de cache: {str(e)}")
            return False
    
    def _load_cached_result(self, source_key: str) -> Optional[ScrapingResult]:
        """Carregar resultado do cache"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{source_key}_result.json")
            
            if not os.path.exists(cache_file):
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return ScrapingResult(
                success=data['success'],
                source_name=data['source_name'],
                documents_found=data.get('documents_found', 0),
                documents_processed=data.get('documents_processed', 0),
                error=data.get('error'),
                execution_time=data.get('execution_time', 0),
                last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
            )
            
        except Exception as e:
            self._log_error(f"Erro ao carregar cache: {str(e)}")
            return None
    
    def _save_cached_result(self, source_key: str, result: ScrapingResult):
        """Salvar resultado no cache"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{source_key}_result.json")
            
            data = {
                'success': result.success,
                'source_name': result.source_name,
                'documents_found': result.documents_found,
                'documents_processed': result.documents_processed,
                'error': result.error,
                'execution_time': result.execution_time,
                'last_update': result.last_update.isoformat() if result.last_update else None
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self._log_error(f"Erro ao salvar cache: {str(e)}")
    
    def _log_error(self, error_msg: str):
        """Log de erro"""
        try:
            print(f"[ERROR] LegalScrapingService: {error_msg}")
        except:
            print(f"[ERROR] LegalScrapingService: {error_msg}")

# Instância global do service
legal_scraping_service = LegalScrapingService()

