"""
SearchService - Busca Semântica e Indexação

Este service gerencia busca semântica, indexação de documentos
e recuperação de contexto relevante para o sistema RAG.
"""

import os
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import hashlib
import pickle

# Imports para processamento de texto e embeddings
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.stem import PorterStemmer
except ImportError:
    # Fallback se bibliotecas não estiverem disponíveis
    TfidfVectorizer = None
    cosine_similarity = None
    nltk = None
    stopwords = None
    word_tokenize = None
    sent_tokenize = None
    PorterStemmer = None

from src.database import db
from src.models import DocumentoUpload, SearchIndex


@dataclass
class SearchResult:
    """Resultado de busca"""
    document_id: int
    title: str
    content: str
    score: float
    source: str
    category: str
    metadata: Dict = None
    highlights: List[str] = None


@dataclass
class IndexStats:
    """Estatísticas do índice"""
    total_documents: int
    indexed_documents: int
    total_chunks: int
    index_size_mb: float
    last_update: datetime
    categories: Dict[str, int]


class SearchService:
    """Service para busca semântica e indexação"""
    
    def __init__(self):
        self.index_dir = os.path.join(os.getcwd(), 'search_index')
        self.vectorizer_path = os.path.join(self.index_dir, 'vectorizer.pkl')
        self.index_path = os.path.join(self.index_dir, 'tfidf_index.pkl')
        self.documents_path = os.path.join(self.index_dir, 'documents.pkl')
        
        # Criar diretório se não existir
        os.makedirs(self.index_dir, exist_ok=True)
        
        # Configurações
        self.max_features = 10000
        self.min_score_threshold = 0.1
        self.max_results = 20
        
        # Inicializar componentes
        self.vectorizer = None
        self.tfidf_matrix = None
        self.documents_data = []
        
        # Carregar índice existente
        self._load_index()
        
        # Inicializar NLTK se disponível
        self._init_nltk()
    
    def index_document(self, 
                      document_id: int,
                      title: str,
                      content: str,
                      source: str = "unknown",
                      category: str = "general",
                      metadata: Dict = None) -> bool:
        """
        Indexar documento para busca
        
        Args:
            document_id: ID único do documento
            title: Título do documento
            content: Conteúdo do documento
            source: Fonte do documento
            category: Categoria do documento
            metadata: Metadados adicionais
            
        Returns:
            True se indexado com sucesso
        """
        try:
            # Verificar se documento já está indexado
            existing_index = SearchIndex.query.filter_by(
                document_id=document_id
            ).first()
            
            if existing_index:
                # Atualizar índice existente
                return self._update_document_index(
                    existing_index, title, content, source, category, metadata
                )
            
            # Processar conteúdo
            processed_content = self._preprocess_text(f"{title} {content}")
            
            if not processed_content.strip():
                return False
            
            # Criar chunks do documento
            chunks = self._create_text_chunks(content)
            
            # Calcular hash do conteúdo
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Salvar no banco de dados
            search_index = SearchIndex(
                document_id=document_id,
                title=title,
                content_hash=content_hash,
                processed_content=processed_content,
                source=source,
                category=category,
                metadata=metadata or {},
                chunks=chunks,
                indexed=True
            )
            
            db.session.add(search_index)
            db.session.commit()
            
            # Adicionar aos dados em memória
            doc_data = {
                'id': document_id,
                'title': title,
                'content': content,
                'processed_content': processed_content,
                'source': source,
                'category': category,
                'metadata': metadata or {},
                'chunks': chunks
            }
            
            self.documents_data.append(doc_data)
            
            # Reconstruir índice TF-IDF
            self._rebuild_tfidf_index()
            
            return True
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro na indexação: {str(e)}")
            return False
    
    def search(self, 
               query: str,
               category: str = None,
               source: str = None,
               max_results: int = None) -> List[SearchResult]:
        """
        Buscar documentos por similaridade semântica
        
        Args:
            query: Consulta de busca
            category: Filtrar por categoria (opcional)
            source: Filtrar por fonte (opcional)
            max_results: Máximo de resultados (opcional)
            
        Returns:
            Lista de resultados ordenados por relevância
        """
        try:
            if not query.strip():
                return []
            
            max_results = max_results or self.max_results
            
            # Processar query
            processed_query = self._preprocess_text(query)
            
            if not processed_query.strip():
                return []
            
            # Verificar se índice está carregado
            if self.vectorizer is None or self.tfidf_matrix is None:
                self._load_index()
            
            if self.vectorizer is None:
                return []
            
            # Vetorizar query
            query_vector = self.vectorizer.transform([processed_query])
            
            # Calcular similaridades
            similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
            
            # Obter índices dos documentos mais similares
            similar_indices = similarities.argsort()[::-1]
            
            results = []
            
            for idx in similar_indices:
                if len(results) >= max_results:
                    break
                
                score = similarities[idx]
                
                if score < self.min_score_threshold:
                    break
                
                if idx >= len(self.documents_data):
                    continue
                
                doc_data = self.documents_data[idx]
                
                # Aplicar filtros
                if category and doc_data.get('category') != category:
                    continue
                
                if source and doc_data.get('source') != source:
                    continue
                
                # Gerar highlights
                highlights = self._generate_highlights(doc_data['content'], query)
                
                result = SearchResult(
                    document_id=doc_data['id'],
                    title=doc_data['title'],
                    content=doc_data['content'][:500] + "..." if len(doc_data['content']) > 500 else doc_data['content'],
                    score=float(score),
                    source=doc_data['source'],
                    category=doc_data['category'],
                    metadata=doc_data.get('metadata', {}),
                    highlights=highlights
                )
                
                results.append(result)
            
            return results
            
        except Exception as e:
            self._log_error(f"Erro na busca: {str(e)}")
            return []
    
    def get_similar_documents(self, 
                             document_id: int,
                             max_results: int = 5) -> List[SearchResult]:
        """
        Encontrar documentos similares a um documento específico
        
        Args:
            document_id: ID do documento de referência
            max_results: Máximo de resultados
            
        Returns:
            Lista de documentos similares
        """
        try:
            # Buscar documento de referência
            ref_doc = None
            ref_idx = None
            
            for idx, doc_data in enumerate(self.documents_data):
                if doc_data['id'] == document_id:
                    ref_doc = doc_data
                    ref_idx = idx
                    break
            
            if not ref_doc:
                return []
            
            # Verificar se índice está carregado
            if self.tfidf_matrix is None:
                self._load_index()
            
            if self.tfidf_matrix is None:
                return []
            
            # Calcular similaridades com o documento de referência
            ref_vector = self.tfidf_matrix[ref_idx:ref_idx+1]
            similarities = cosine_similarity(ref_vector, self.tfidf_matrix).flatten()
            
            # Remover o próprio documento
            similarities[ref_idx] = 0
            
            # Obter documentos mais similares
            similar_indices = similarities.argsort()[::-1][:max_results]
            
            results = []
            
            for idx in similar_indices:
                score = similarities[idx]
                
                if score < self.min_score_threshold:
                    break
                
                doc_data = self.documents_data[idx]
                
                result = SearchResult(
                    document_id=doc_data['id'],
                    title=doc_data['title'],
                    content=doc_data['content'][:300] + "..." if len(doc_data['content']) > 300 else doc_data['content'],
                    score=float(score),
                    source=doc_data['source'],
                    category=doc_data['category'],
                    metadata=doc_data.get('metadata', {})
                )
                
                results.append(result)
            
            return results
            
        except Exception as e:
            self._log_error(f"Erro na busca de similares: {str(e)}")
            return []
    
    def rebuild_index(self) -> bool:
        """
        Reconstruir índice completo
        
        Returns:
            True se reconstruído com sucesso
        """
        try:
            # Limpar dados em memória
            self.documents_data = []
            
            # Buscar todos os documentos indexados
            indexed_docs = SearchIndex.query.filter_by(indexed=True).all()
            
            for search_index in indexed_docs:
                doc_data = {
                    'id': search_index.document_id,
                    'title': search_index.title,
                    'content': search_index.processed_content,
                    'processed_content': search_index.processed_content,
                    'source': search_index.source,
                    'category': search_index.category,
                    'metadata': search_index.metadata or {},
                    'chunks': search_index.chunks or []
                }
                
                self.documents_data.append(doc_data)
            
            # Reconstruir índice TF-IDF
            return self._rebuild_tfidf_index()
            
        except Exception as e:
            self._log_error(f"Erro na reconstrução do índice: {str(e)}")
            return False
    
    def remove_document(self, document_id: int) -> bool:
        """
        Remover documento do índice
        
        Args:
            document_id: ID do documento
            
        Returns:
            True se removido com sucesso
        """
        try:
            # Remover do banco
            search_index = SearchIndex.query.filter_by(
                document_id=document_id
            ).first()
            
            if search_index:
                db.session.delete(search_index)
                db.session.commit()
            
            # Remover dos dados em memória
            self.documents_data = [
                doc for doc in self.documents_data 
                if doc['id'] != document_id
            ]
            
            # Reconstruir índice
            self._rebuild_tfidf_index()
            
            return True
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro na remoção: {str(e)}")
            return False
    
    def get_index_stats(self) -> IndexStats:
        """
        Obter estatísticas do índice
        
        Returns:
            IndexStats com estatísticas
        """
        try:
            # Estatísticas do banco
            total_docs = DocumentoUpload.query.count()
            indexed_docs = SearchIndex.query.filter_by(indexed=True).count()
            
            # Contar chunks
            total_chunks = db.session.query(
                db.func.sum(db.func.json_array_length(SearchIndex.chunks))
            ).scalar() or 0
            
            # Estatísticas por categoria
            category_stats = db.session.query(
                SearchIndex.category,
                db.func.count(SearchIndex.id).label('count')
            ).group_by(SearchIndex.category).all()
            
            categories = {cat: count for cat, count in category_stats}
            
            # Tamanho do índice
            index_size = 0
            if os.path.exists(self.index_path):
                index_size = os.path.getsize(self.index_path) / (1024 * 1024)  # MB
            
            # Última atualização
            last_update = db.session.query(
                db.func.max(SearchIndex.updated_at)
            ).scalar() or datetime.utcnow()
            
            return IndexStats(
                total_documents=total_docs,
                indexed_documents=indexed_docs,
                total_chunks=total_chunks,
                index_size_mb=round(index_size, 2),
                last_update=last_update,
                categories=categories
            )
            
        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}")
            return IndexStats(
                total_documents=0,
                indexed_documents=0,
                total_chunks=0,
                index_size_mb=0,
                last_update=datetime.utcnow(),
                categories={}
            )
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de busca
        
        Returns:
            Dict com status do sistema
        """
        try:
            stats = self.get_index_stats()
            
            # Testar busca
            test_results = self.search("test query", max_results=1)
            search_working = True
            
            # Verificar arquivos de índice
            index_files_exist = {
                'vectorizer': os.path.exists(self.vectorizer_path),
                'index': os.path.exists(self.index_path),
                'documents': os.path.exists(self.documents_path)
            }
            
            # Verificar bibliotecas
            libraries_available = {
                'sklearn': TfidfVectorizer is not None,
                'nltk': nltk is not None
            }
            
            status = "healthy"
            if stats.indexed_documents == 0:
                status = "warning"
            elif not all(libraries_available.values()):
                status = "degraded"
            
            return {
                "status": status,
                "statistics": {
                    "total_documents": stats.total_documents,
                    "indexed_documents": stats.indexed_documents,
                    "total_chunks": stats.total_chunks,
                    "index_size_mb": stats.index_size_mb,
                    "categories": stats.categories
                },
                "index_files": index_files_exist,
                "libraries": libraries_available,
                "search_test": {
                    "working": search_working,
                    "results_count": len(test_results)
                },
                "config": {
                    "max_features": self.max_features,
                    "min_score_threshold": self.min_score_threshold,
                    "max_results": self.max_results
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
    
    def _init_nltk(self):
        """Inicializar NLTK se disponível"""
        if nltk is None:
            return
        
        try:
            # Baixar recursos necessários
            nltk.download('punkt', quiet=True)
            nltk.download('stopwords', quiet=True)
        except:
            pass
    
    def _preprocess_text(self, text: str) -> str:
        """Pré-processar texto para indexação"""
        if not text:
            return ""
        
        try:
            # Converter para minúsculas
            text = text.lower()
            
            # Remover caracteres especiais (manter apenas letras, números e espaços)
            import re
            text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
            
            # Remover espaços extras
            text = ' '.join(text.split())
            
            # Se NLTK estiver disponível, usar processamento mais avançado
            if word_tokenize and stopwords:
                try:
                    # Tokenizar
                    tokens = word_tokenize(text)
                    
                    # Remover stopwords
                    stop_words = set(stopwords.words('english'))
                    stop_words.update(set(stopwords.words('portuguese')))
                    
                    tokens = [token for token in tokens if token not in stop_words]
                    
                    # Stemming
                    if PorterStemmer:
                        stemmer = PorterStemmer()
                        tokens = [stemmer.stem(token) for token in tokens]
                    
                    text = ' '.join(tokens)
                except:
                    pass
            
            return text
            
        except Exception as e:
            self._log_error(f"Erro no pré-processamento: {str(e)}")
            return text.lower()
    
    def _create_text_chunks(self, text: str, chunk_size: int = 1000) -> List[str]:
        """Criar chunks de texto"""
        if not text:
            return []
        
        chunks = []
        
        # Se NLTK estiver disponível, dividir por sentenças
        if sent_tokenize:
            try:
                sentences = sent_tokenize(text)
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) <= chunk_size:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                return chunks
            except:
                pass
        
        # Fallback: dividir por caracteres
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
    
    def _rebuild_tfidf_index(self) -> bool:
        """Reconstruir índice TF-IDF"""
        try:
            if not self.documents_data:
                return True
            
            # Preparar corpus
            corpus = [doc['processed_content'] for doc in self.documents_data]
            
            if not corpus:
                return True
            
            # Criar ou atualizar vectorizer
            if TfidfVectorizer is None:
                self._log_error("TfidfVectorizer não disponível")
                return False
            
            self.vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1,
                max_df=0.95
            )
            
            # Criar matriz TF-IDF
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
            
            # Salvar índice
            self._save_index()
            
            return True
            
        except Exception as e:
            self._log_error(f"Erro na reconstrução do TF-IDF: {str(e)}")
            return False
    
    def _save_index(self):
        """Salvar índice em disco"""
        try:
            # Salvar vectorizer
            with open(self.vectorizer_path, 'wb') as f:
                pickle.dump(self.vectorizer, f)
            
            # Salvar matriz TF-IDF
            with open(self.index_path, 'wb') as f:
                pickle.dump(self.tfidf_matrix, f)
            
            # Salvar dados dos documentos
            with open(self.documents_path, 'wb') as f:
                pickle.dump(self.documents_data, f)
                
        except Exception as e:
            self._log_error(f"Erro ao salvar índice: {str(e)}")
    
    def _load_index(self):
        """Carregar índice do disco"""
        try:
            # Carregar vectorizer
            if os.path.exists(self.vectorizer_path):
                with open(self.vectorizer_path, 'rb') as f:
                    self.vectorizer = pickle.load(f)
            
            # Carregar matriz TF-IDF
            if os.path.exists(self.index_path):
                with open(self.index_path, 'rb') as f:
                    self.tfidf_matrix = pickle.load(f)
            
            # Carregar dados dos documentos
            if os.path.exists(self.documents_path):
                with open(self.documents_path, 'rb') as f:
                    self.documents_data = pickle.load(f)
                    
        except Exception as e:
            self._log_error(f"Erro ao carregar índice: {str(e)}")
            # Resetar em caso de erro
            self.vectorizer = None
            self.tfidf_matrix = None
            self.documents_data = []
    
    def _generate_highlights(self, content: str, query: str, max_highlights: int = 3) -> List[str]:
        """Gerar highlights do conteúdo baseado na query"""
        try:
            if not content or not query:
                return []
            
            query_words = query.lower().split()
            content_lower = content.lower()
            
            highlights = []
            sentences = content.split('.')
            
            for sentence in sentences:
                sentence_lower = sentence.lower()
                
                # Verificar se a sentença contém palavras da query
                matches = sum(1 for word in query_words if word in sentence_lower)
                
                if matches > 0:
                    # Limitar tamanho da sentença
                    if len(sentence) > 200:
                        sentence = sentence[:200] + "..."
                    
                    highlights.append(sentence.strip())
                    
                    if len(highlights) >= max_highlights:
                        break
            
            return highlights
            
        except Exception as e:
            self._log_error(f"Erro na geração de highlights: {str(e)}")
            return []
    
    def _update_document_index(self, search_index, title, content, source, category, metadata):
        """Atualizar índice de documento existente"""
        try:
            # Processar novo conteúdo
            processed_content = self._preprocess_text(f"{title} {content}")
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Verificar se conteúdo mudou
            if search_index.content_hash == content_hash:
                return True  # Sem mudanças
            
            # Atualizar no banco
            search_index.title = title
            search_index.content_hash = content_hash
            search_index.processed_content = processed_content
            search_index.source = source
            search_index.category = category
            search_index.metadata = metadata or {}
            search_index.chunks = self._create_text_chunks(content)
            search_index.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Atualizar dados em memória
            for doc_data in self.documents_data:
                if doc_data['id'] == search_index.document_id:
                    doc_data.update({
                        'title': title,
                        'content': content,
                        'processed_content': processed_content,
                        'source': source,
                        'category': category,
                        'metadata': metadata or {},
                        'chunks': search_index.chunks
                    })
                    break
            
            # Reconstruir índice
            self._rebuild_tfidf_index()
            
            return True
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro na atualização: {str(e)}")
            return False
    
    def _log_error(self, error_msg: str):
        """Log de erro"""
        try:
            print(f"[ERROR] SearchService: {error_msg}")
        except:
            print(f"[ERROR] SearchService: {error_msg}")

# Instância global do service
search_service = SearchService()

