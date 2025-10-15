"""
MCPService - Model Context Protocol

Este service gerencia o sistema MCP (Model Context Protocol) para integração
com fontes jurídicas dos EUA e Brasil, incluindo web scraping e indexação.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

import requests

from src.extensions import db
from src.models import FonteJuridica


@dataclass
class ScrapingResult:
    """Resultado do web scraping"""
    success: bool
    source_name: str
    documents_found: int = 0
    content: List[Dict] = None
    error: Optional[str] = None
    last_updated: datetime = None


@dataclass
class MCPDocument:
    """Documento do sistema MCP"""
    title: str
    content: str
    source: str
    url: str
    category: str
    metadata: Dict = None
    relevance_score: float = 0.0


class MCPService:
    """Service para Model Context Protocol"""

    def __init__(self):
        self.sources_config = {
            'usa': {
                'irs': {
                    'name': 'IRS - Internal Revenue Service',
                    'base_url': 'https://www.irs.gov',
                    'endpoints': [
                        '/businesses/international-businesses',
                        '/individuals/international-taxpayers',
                        '/tax-professionals/international-tax-compliance'
                    ],
                    'category': 'international_tax'
                },
                'sec': {
                    'name': 'SEC - Securities and Exchange Commission',
                    'base_url': 'https://www.sec.gov',
                    'endpoints': [
                        '/investment/investment-adviser-regulation',
                        '/rules/final',
                        '/divisions/investment'
                    ],
                    'category': 'investment_regulation'
                },
                'treasury': {
                    'name': 'US Treasury Department',
                    'base_url': 'https://home.treasury.gov',
                    'endpoints': [
                        '/policy-issues/international',
                        '/policy-issues/tax-policy'
                    ],
                    'category': 'international_tax'
                }
            },
            'brazil': {
                'receita_federal': {
                    'name': 'Receita Federal do Brasil',
                    'base_url': 'https://www.gov.br/receitafederal',
                    'endpoints': [
                        '/pt-br/assuntos/orientacao-tributaria/acordos-internacionais',
                        '/pt-br/assuntos/orientacao-tributaria/legislacao',
                        '/pt-br/assuntos/orientacao-tributaria/regimes-aduaneiros-especiais'
                    ],
                    'category': 'tax_compliance'
                },
                'cvm': {
                    'name': 'Comissão de Valores Mobiliários',
                    'base_url': 'https://www.gov.br/cvm',
                    'endpoints': [
                        '/pt-br/assuntos/regulacao',
                        '/pt-br/assuntos/orientacoes',
                        '/pt-br/assuntos/normas'
                    ],
                    'category': 'investment_regulation'
                },
                'bacen': {
                    'name': 'Banco Central do Brasil',
                    'base_url': 'https://www.bcb.gov.br',
                    'endpoints': [
                        '/estabilidadefinanceira/regulacao',
                        '/acessoinformacao/legis',
                        '/pre/normativos'
                    ],
                    'category': 'financial_regulation'
                }
            }
        }

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        self.request_delay = 2  # Segundos entre requisições
        self.timeout = 30

    def scrape_all_sources(self, force_update: bool = False) -> Dict[str, ScrapingResult]:
        """
        Fazer scraping de todas as fontes configuradas
        
        Args:
            force_update: Forçar atualização mesmo se recente
            
        Returns:
            Dict com resultados por fonte
        """
        results = {}

        for country, sources in self.sources_config.items():
            for source_key, source_config in sources.items():
                try:
                    # Verificar se precisa atualizar
                    if not force_update and not self._needs_update(source_key):
                        continue

                    result = self._scrape_source(source_key, source_config)
                    results[f"{country}_{source_key}"] = result

                    # Delay entre fontes
                    time.sleep(self.request_delay)

                except Exception as e:
                    results[f"{country}_{source_key}"] = ScrapingResult(
                        success=False,
                        source_name=source_config['name'],
                        error=str(e)
                    )

        return results

    def scrape_source(self, source_key: str, force_update: bool = False) -> ScrapingResult:
        """
        Fazer scraping de uma fonte específica
        
        Args:
            source_key: Chave da fonte (ex: 'usa_irs', 'brazil_receita_federal')
            force_update: Forçar atualização
            
        Returns:
            ScrapingResult com resultado do scraping
        """
        try:
            # Encontrar configuração da fonte
            source_config = None
            for country, sources in self.sources_config.items():
                for key, config in sources.items():
                    if f"{country}_{key}" == source_key:
                        source_config = config
                        break
                if source_config:
                    break

            if not source_config:
                return ScrapingResult(
                    success=False,
                    source_name=source_key,
                    error="Fonte não encontrada"
                )

            # Verificar se precisa atualizar
            if not force_update and not self._needs_update(source_key):
                return ScrapingResult(
                    success=True,
                    source_name=source_config['name'],
                    documents_found=0,
                    content=[],
                    error="Fonte já atualizada recentemente"
                )

            return self._scrape_source(source_key, source_config)

        except Exception as e:
            return ScrapingResult(
                success=False,
                source_name=source_key,
                error=str(e)
            )

    def get_legal_context(self, query: str, max_results: int = 5) -> List[MCPDocument]:
        """
        Obter contexto jurídico relevante para uma consulta
        
        Args:
            query: Consulta/pergunta
            max_results: Máximo de documentos a retornar
            
        Returns:
            Lista de documentos relevantes
        """
        try:
            # Buscar documentos relevantes no banco
            # Por enquanto, simulação com dados estáticos
            mock_documents = [
                MCPDocument(
                    title="International Tax Compliance Guidelines",
                    content="Guidelines for international tax compliance including offshore structures...",
                    source="IRS",
                    url="https://www.irs.gov/businesses/international-businesses",
                    category="international_tax",
                    metadata={"country": "USA", "type": "guideline"},
                    relevance_score=0.95
                ),
                MCPDocument(
                    title="Acordos Internacionais - Receita Federal",
                    content="Informações sobre acordos internacionais para evitar dupla tributação...",
                    source="Receita Federal",
                    url="https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/acordos-internacionais",
                    category="tax_compliance",
                    metadata={"country": "Brazil", "type": "regulation"},
                    relevance_score=0.88
                ),
                MCPDocument(
                    title="Trust Structures and Tax Implications",
                    content="Analysis of trust structures for wealth planning and tax optimization...",
                    source="Treasury Department",
                    url="https://home.treasury.gov/policy-issues/tax-policy",
                    category="wealth_planning",
                    metadata={"country": "USA", "type": "analysis"},
                    relevance_score=0.82
                )
            ]

            # Filtrar por relevância e limitar resultados
            relevant_docs = [doc for doc in mock_documents if doc.relevance_score > 0.7]
            return relevant_docs[:max_results]

        except Exception as e:
            self._log_error(f"Erro ao obter contexto jurídico: {str(e)}")
            return []

    def get_source_status(self) -> Dict[str, Any]:
        """
        Obter status de todas as fontes
        
        Returns:
            Dict com status das fontes
        """
        try:
            status = {}

            for country, sources in self.sources_config.items():
                status[country] = {}

                for source_key, source_config in sources.items():
                    # Buscar última atualização no banco
                    fonte = FonteJuridica.query.filter_by(
                        source_key=f"{country}_{source_key}"
                    ).first()

                    if fonte:
                        status[country][source_key] = {
                            'name': source_config['name'],
                            'status': 'active' if fonte.active else 'inactive',
                            'last_update': fonte.last_scraped.isoformat() if fonte.last_scraped else None,
                            'documents_count': fonte.documents_count or 0,
                            'category': source_config['category']
                        }
                    else:
                        status[country][source_key] = {
                            'name': source_config['name'],
                            'status': 'not_initialized',
                            'last_update': None,
                            'documents_count': 0,
                            'category': source_config['category']
                        }

            return status

        except Exception as e:
            self._log_error(f"Erro ao obter status das fontes: {str(e)}")
            return {}

    def update_source_config(self, source_key: str, config: Dict) -> bool:
        """
        Atualizar configuração de uma fonte
        
        Args:
            source_key: Chave da fonte
            config: Nova configuração
            
        Returns:
            True se atualizado com sucesso
        """
        try:
            # Encontrar e atualizar fonte no banco
            fonte = FonteJuridica.query.filter_by(source_key=source_key).first()

            if not fonte:
                # Criar nova fonte
                fonte = FonteJuridica(
                    source_key=source_key,
                    name=config.get('name', ''),
                    base_url=config.get('base_url', ''),
                    category=config.get('category', 'general'),
                    config=config,
                    active=True
                )
                db.session.add(fonte)
            else:
                # Atualizar fonte existente
                fonte.name = config.get('name', fonte.name)
                fonte.base_url = config.get('base_url', fonte.base_url)
                fonte.category = config.get('category', fonte.category)
                fonte.config = config
                fonte.updated_at = datetime.utcnow()

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro ao atualizar configuração: {str(e)}")
            return False

    def get_categories_stats(self) -> Dict[str, Any]:
        """
        Obter estatísticas por categoria
        
        Returns:
            Dict com estatísticas
        """
        try:
            # Contar documentos por categoria
            categories = {}

            for country, sources in self.sources_config.items():
                for source_key, source_config in sources.items():
                    category = source_config['category']

                    if category not in categories:
                        categories[category] = {
                            'name': category.replace('_', ' ').title(),
                            'sources': 0,
                            'documents': 0,
                            'countries': set()
                        }

                    categories[category]['sources'] += 1
                    categories[category]['countries'].add(country.upper())

                    # Buscar contagem de documentos
                    fonte = FonteJuridica.query.filter_by(
                        source_key=f"{country}_{source_key}"
                    ).first()

                    if fonte and fonte.documents_count:
                        categories[category]['documents'] += fonte.documents_count

            # Converter sets para listas
            for category in categories.values():
                category['countries'] = list(category['countries'])

            return categories

        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}")
            return {}

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema MCP
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Testar conectividade com algumas fontes
            connectivity_tests = {}

            test_sources = [
                ('usa', 'irs'),
                ('brazil', 'receita_federal')
            ]

            for country, source_key in test_sources:
                source_config = self.sources_config[country][source_key]

                try:
                    response = self.session.head(
                        source_config['base_url'],
                        timeout=10
                    )
                    connectivity_tests[f"{country}_{source_key}"] = {
                        'status': 'reachable' if response.status_code < 400 else 'unreachable',
                        'response_code': response.status_code,
                        'response_time': response.elapsed.total_seconds()
                    }
                except Exception as e:
                    connectivity_tests[f"{country}_{source_key}"] = {
                        'status': 'unreachable',
                        'error': str(e)
                    }

            # Estatísticas do banco
            total_sources = FonteJuridica.query.count()
            active_sources = FonteJuridica.query.filter_by(active=True).count()

            return {
                "status": "healthy" if active_sources > 0 else "warning",
                "sources": {
                    "total_configured": sum(len(sources) for sources in self.sources_config.values()),
                    "total_in_db": total_sources,
                    "active": active_sources
                },
                "connectivity": connectivity_tests,
                "config": {
                    "request_delay": self.request_delay,
                    "timeout": self.timeout,
                    "countries": list(self.sources_config.keys())
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

    def _scrape_source(self, source_key: str, source_config: Dict) -> ScrapingResult:
        """Fazer scraping de uma fonte específica"""
        try:
            documents = []
            base_url = source_config['base_url']

            for endpoint in source_config['endpoints']:
                try:
                    url = urljoin(base_url, endpoint)

                    response = self.session.get(url, timeout=self.timeout)
                    response.raise_for_status()

                    # Extrair conteúdo (simulação)
                    content = self._extract_content_from_html(response.text, url)

                    if content:
                        documents.append({
                            'title': content.get('title', 'Untitled'),
                            'content': content.get('content', ''),
                            'url': url,
                            'category': source_config['category'],
                            'scraped_at': datetime.utcnow().isoformat()
                        })

                    # Delay entre requisições
                    time.sleep(self.request_delay)

                except requests.exceptions.RequestException as e:
                    self._log_error(f"Erro ao acessar {url}: {str(e)}")
                    continue

            # Salvar no banco de dados
            self._save_scraped_data(source_key, source_config, documents)

            return ScrapingResult(
                success=True,
                source_name=source_config['name'],
                documents_found=len(documents),
                content=documents,
                last_updated=datetime.utcnow()
            )

        except Exception as e:
            return ScrapingResult(
                success=False,
                source_name=source_config['name'],
                error=str(e)
            )

    def _extract_content_from_html(self, html: str, url: str) -> Optional[Dict]:
        """Extrair conteúdo relevante do HTML"""
        try:
            # Simulação de extração de conteúdo
            # Em implementação real, usaria BeautifulSoup ou similar

            # Detectar tipo de conteúdo baseado na URL
            if 'irs.gov' in url:
                return {
                    'title': 'IRS International Tax Guidance',
                    'content': 'Guidelines for international tax compliance, offshore structures, and reporting requirements for US taxpayers with foreign assets.'
                }
            elif 'receitafederal' in url:
                return {
                    'title': 'Orientações Tributárias - Receita Federal',
                    'content': 'Orientações sobre tributação internacional, acordos para evitar dupla tributação e compliance fiscal para residentes brasileiros.'
                }
            elif 'sec.gov' in url:
                return {
                    'title': 'SEC Investment Adviser Regulations',
                    'content': 'Regulations and guidance for investment advisers, including international compliance requirements.'
                }
            elif 'cvm' in url:
                return {
                    'title': 'Regulamentação CVM',
                    'content': 'Normas e orientações da CVM sobre mercado de capitais, fundos de investimento e estruturas internacionais.'
                }
            else:
                return {
                    'title': f'Legal Document from {urlparse(url).netloc}',
                    'content': 'Legal guidance and regulatory information relevant to wealth planning and international tax compliance.'
                }

        except Exception as e:
            self._log_error(f"Erro na extração de conteúdo: {str(e)}")
            return None

    def _save_scraped_data(self, source_key: str, source_config: Dict, documents: List[Dict]):
        """Salvar dados coletados no banco"""
        try:
            # Buscar ou criar fonte
            fonte = FonteJuridica.query.filter_by(source_key=source_key).first()

            if not fonte:
                fonte = FonteJuridica(
                    source_key=source_key,
                    name=source_config['name'],
                    base_url=source_config['base_url'],
                    category=source_config['category'],
                    config=source_config,
                    active=True
                )
                db.session.add(fonte)

            # Atualizar informações da fonte
            fonte.last_scraped = datetime.utcnow()
            fonte.documents_count = len(documents)
            fonte.last_content = documents
            fonte.updated_at = datetime.utcnow()

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro ao salvar dados: {str(e)}")

    def _needs_update(self, source_key: str) -> bool:
        """Verificar se fonte precisa ser atualizada"""
        try:
            fonte = FonteJuridica.query.filter_by(source_key=source_key).first()

            if not fonte or not fonte.last_scraped:
                return True

            # Atualizar se passou mais de 24 horas
            time_diff = datetime.utcnow() - fonte.last_scraped
            return time_diff > timedelta(hours=24)

        except Exception as e:
            self._log_error(f"Erro ao verificar necessidade de atualização: {str(e)}")
            return True

    def _log_error(self, error_msg: str):
        """Log de erro"""
        try:
            print(f"[ERROR] MCPService: {error_msg}")
        except:
            print(f"[ERROR] MCPService: {error_msg}")


# Instância global do service
mcp_service = MCPService()
