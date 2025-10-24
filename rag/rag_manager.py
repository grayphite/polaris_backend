"""
RAG Manager - Core of the legal RAG system
Manages embeddings, vector store, and semantic search
"""

import json
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Safe imports with fallback
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from .document_processor import DocumentProcessor
from .utils import RAGUtils

# Import configuration system
try:
    from .config.rag_config import get_rag_config_values
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

logger = logging.getLogger(__name__)


class JuridicalRAGManager:
    """Main manager for the legal RAG system"""

    def __init__(self,
                 chroma_db_path: str = None,
                 collection_name: str = None,
                 embedding_model: str = None):
        """
        Initialize the RAG Manager

        Args:
            chroma_db_path: Path to the vector database (optional, uses config)
            collection_name: Collection name (optional, uses config)
            embedding_model: Embedding model name (optional, uses config)
        """
        # Load configuration
        if CONFIG_AVAILABLE:
            config = get_rag_config_values()
            self.chroma_db_path = Path(chroma_db_path or config.database.default_db_path)
            self.collection_name = collection_name or config.database.default_collection_name
            self.embedding_model_name = embedding_model or config.database.default_embedding_model
        else:
            # Fallback to hardcoded values
            self.chroma_db_path = Path(chroma_db_path or "./chroma_db")
            self.collection_name = collection_name or "juridical_documents"
            self.embedding_model_name = embedding_model or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

        # Check dependencies
        self.rag_available = self._check_dependencies()

        if not self.rag_available:
            logger.warning("RAG is not fully functional. Check dependencies.")
            self.client = None
            self.collection = None
            self.embedding_model = None
            return

        # Initialize components
        try:
            self.document_processor = DocumentProcessor()
            self.client = self._init_chromadb()
            self.collection = self._init_collection()
            self.embedding_model = self._init_embedding_model()

            logger.info("RAG Manager initialized successfully")
            logger.info(f"Vector DB path: {self.chroma_db_path}")
            logger.info(f"Embedding model: {self.embedding_model_name}")

        except Exception as e:
            logger.error(f"Error initializing RAG Manager: {str(e)}")
            self.rag_available = False
            self.client = None
            self.collection = None
            self.embedding_model = None

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available"""
        if not CHROMADB_AVAILABLE:
            logger.error("ChromaDB is not installed")
            return False

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.error("sentence-transformers is not installed")
            return False

        return True

    def _init_chromadb(self):
        """Initialize ChromaDB client"""
        try:
            # Load connection configuration
            connection_type = "local"  # Default
            cloud_config = {}

            # Check environment variables first (override config)
            import os
            env_connection_type = os.getenv('CHROMA_CONNECTION_TYPE')
            env_host = os.getenv('CHROMA_HOST')
            env_port = os.getenv('CHROMA_PORT')
            env_ssl = os.getenv('CHROMA_SSL')
            env_api_key = os.getenv('CHROMA_API_KEY')
            env_tenant = os.getenv('CHROMA_TENANT')
            env_database = os.getenv('CHROMA_DATABASE')

            if env_connection_type or env_host or env_api_key:
                # Use environment variables
                connection_type = env_connection_type or "cloud"
                cloud_config = {
                    'api_key': env_api_key,
                    'tenant': env_tenant,
                    'database': env_database,
                    'host': env_host,
                    'port': int(env_port) if env_port else 8000,
                    'ssl': env_ssl and env_ssl.lower() == 'true',
                    'headers': {'Authorization': f'Bearer {env_api_key}'} if env_api_key else {}
                }
            elif CONFIG_AVAILABLE:
                # Use config file
                config = get_rag_config_values()
                connection_type = getattr(config.database, 'connection_type', 'local')
                cloud_config = getattr(config.database, 'cloud_config', {})

            # Initialize based on connection type
            if connection_type == "cloud":
                # TryChroma CloudClient connection (only supported cloud option)
                if cloud_config.get('api_key') and cloud_config.get('tenant') and cloud_config.get('database'):
                    client = chromadb.CloudClient(
                        api_key=cloud_config.get('api_key'),
                        tenant=cloud_config.get('tenant'),
                        database=cloud_config.get('database')
                    )
                    logger.info(f"ChromaDB TryChroma client initialized: tenant={cloud_config.get('tenant')}, database={cloud_config.get('database')}")
                else:
                    # Cloud connection requested but missing TryChroma credentials, fallback to local
                    logger.warning("Cloud connection requested but missing TryChroma credentials (CHROMA_API_KEY, CHROMA_TENANT, CHROMA_DATABASE), falling back to local")
                    self.chroma_db_path.mkdir(parents=True, exist_ok=True)
                    client = chromadb.PersistentClient(
                        path=str(self.chroma_db_path),
                        settings=Settings(anonymized_telemetry=False)
                    )
                    logger.info(f"ChromaDB local client initialized (fallback): {self.chroma_db_path}")
            else:
                # Local ChromaDB connection (default)
                self.chroma_db_path.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(
                    path=str(self.chroma_db_path),
                    settings=Settings(anonymized_telemetry=False)
                )
                logger.info(f"ChromaDB local client initialized: {self.chroma_db_path}")

            return client

        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {str(e)}")
            raise

    def _init_collection(self):
        """Initialize or load collection"""
        try:
            # Try to load existing collection
            try:
                collection = self.client.get_collection(
                    name=self.collection_name)
                logger.info(f"Collection '{self.collection_name}' loaded")
            except Exception:
                # Create new collection
                collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={
                        "description": "Legal documents processed by POLARIS"
                    }
                )
                logger.info(f"New collection '{self.collection_name}' created")

            return collection

        except Exception as e:
            logger.error(f"Error initializing collection: {str(e)}")
            raise

    def _init_embedding_model(self):
        """Initialize embedding model"""
        try:
            model = SentenceTransformer(self.embedding_model_name)
            logger.info(f"Embedding model loaded: {self.embedding_model_name}")
            return model

        except Exception as e:
            logger.error(f"Error loading embedding model: {str(e)}")
            # Fallback
            try:
                model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.warning("Using fallback model: all-MiniLM-L6-v2")
                return model
            except Exception as fallback_error:
                raise Exception(
                    f"Could not load embedding model: {str(fallback_error)}"
                )

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> bool:
        """
        Add processed chunks directly to the vector store with batch processing

        Args:
            chunks: List of processed document chunks

        Returns:
            bool: Success status
        """
        if not self.rag_available:
            logger.error("RAG is not available")
            return False

        try:
            if not chunks:
                logger.warning("No chunks provided")
                return False

            # Get batch size from config
            batch_size = 500  # Default batch size
            if CONFIG_AVAILABLE:
                try:
                    config = get_rag_config_values()
                    batch_size = getattr(config.database, 'chunk_batch_size', 500)
                except:
                    pass

            logger.info(f"Processing {len(chunks)} chunks in batches of {batch_size}")

            # Process chunks in batches
            total_added = 0
            for batch_start in range(0, len(chunks), batch_size):
                batch_end = min(batch_start + batch_size, len(chunks))
                batch_chunks = chunks[batch_start:batch_end]
                
                logger.info(f"Processing batch {batch_start//batch_size + 1}: chunks {batch_start+1}-{batch_end}")

                # Prepare data for ChromaDB
                documents = []
                metadatas = []
                ids = []

                for i, chunk in enumerate(batch_chunks):
                    documents.append(chunk['text'])

                    # Prepare metadata for ChromaDB (flatten nested dicts)
                    document_metadata = chunk.get('document_metadata', {})
                    metadata = {
                        'source_file': chunk.get('source_file', 'unknown'),
                        'source_path': chunk.get('source_path', ''),
                        'chunk_id': chunk.get('chunk_id', batch_start + i),
                        'char_count': chunk.get('char_count', 0),
                        'type': chunk.get('type', 'text'),
                        # Flatten document metadata
                        'filename': document_metadata.get('filename', ''),
                        'extension': document_metadata.get('extension', ''),
                        'size_bytes': document_metadata.get('size_bytes', 0),
                        'text_length': document_metadata.get('text_length', 0),
                        'word_count': document_metadata.get('word_count', 0),
                        'processed_by': document_metadata.get('processed_by', ''),
                        'extraction_method': document_metadata.get('extraction_method', '')
                    }
                    metadatas.append(metadata)
                    ids.append(f"chunk_{batch_start + i}_{chunk.get('source_file', 'unknown')}")

                # Add batch to collection
                try:
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                    total_added += len(batch_chunks)
                    logger.info(f"Added batch of {len(batch_chunks)} chunks (total: {total_added})")
                    
                except Exception as batch_error:
                    logger.error(f"Error adding batch {batch_start//batch_size + 1}: {str(batch_error)}")
                    # Continue with next batch instead of failing completely
                    continue

            logger.info(f"Successfully added {total_added} out of {len(chunks)} chunks to collection")
            return total_added > 0

        except Exception as e:
            logger.error(f"Error adding chunks: {str(e)}")
            return False

    def add_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Add documents to the vector store

        Args:
            file_paths: List of file paths

        Returns:
            Dict with processing results
        """
        if not self.rag_available:
            return {
                'success': False,
                'error': 'RAG is not available',
                'processed_documents': 0,
                'total_chunks': 0
            }

        try:
            # Process documents
            processing_result = self.document_processor.process_multiple_documents(file_paths)

            if not processing_result['successful']:
                return {
                    'success': False,
                    'error': 'No document was processed successfully',
                    'failed_files': processing_result['failed'],
                    'processed_documents': 0,
                    'total_chunks': 0
                }

            # Prepare data for ChromaDB insertion
            all_chunks = []
            all_embeddings = []
            all_metadatas = []
            all_ids = []

            for doc_result in processing_result['successful']:
                chunks = doc_result['chunks']
                source_file = doc_result['source_file']

                for chunk in chunks:
                    # Chunk text
                    chunk_text = chunk['text']
                    all_chunks.append(chunk_text)

                    # Generate embedding
                    embedding = self.embedding_model.encode(chunk_text).tolist()
                    all_embeddings.append(embedding)

                    # Metadata
                    metadata = {
                        'source_file': source_file,
                        'chunk_id': chunk['chunk_id'],
                        'chunk_type': chunk['type'],
                        'char_count': chunk['char_count'],
                        'word_count': len(chunk_text.split()),
                        'processed_at': datetime.now().isoformat(),
                        'file_metadata': json.dumps(chunk['document_metadata'])
                    }
                    all_metadatas.append(metadata)

                    # Unique ID
                    chunk_id = f"{source_file}_{chunk['chunk_id']}_{datetime.now().timestamp()}"
                    all_ids.append(chunk_id)

            # Insert into ChromaDB
            self.collection.add(
                embeddings=all_embeddings,
                documents=all_chunks,
                metadatas=all_metadatas,
                ids=all_ids
            )

            # PersistentClient persists automatically

            result = {
                'success': True,
                'processed_documents': len(processing_result['successful']),
                'total_chunks': len(all_chunks),
                'failed_files': processing_result['failed'],
                'processing_summary': processing_result['processing_summary']
            }

            logger.info(f"Documents added to RAG: {result}")
            return result

        except Exception as e:
            error_msg = f"Error adding documents to RAG: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'processed_documents': 0,
                'total_chunks': 0
            }

    def search_relevant_docs(self,
                          query: str,
                          k: int = None,
                          score_threshold: float = None) -> List[Dict[str, Any]]:
        """
        Search for relevant documents given a query

        Args:
            query: Legal query
            k: Max results (optional, uses config default)
            score_threshold: Minimum relevance threshold (optional, uses config default)

        Returns:
            List of relevant document chunks
        """
        # Load configuration defaults
        if CONFIG_AVAILABLE:
            config = get_rag_config_values()
            k = k or config.search.default_max_results
            score_threshold = score_threshold or config.search.default_score_threshold
        else:
            k = k or 5
            score_threshold = score_threshold or 0.05

        if not self.rag_available:
            logger.warning("RAG not available for search")
            return []

        try:
            # Query embedding
            query_embedding = self.embedding_model.encode(query).tolist()

            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=['documents', 'metadatas', 'distances']
            )

            # Process results
            relevant_docs = []

            if results['documents'] and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results['metadatas'][0]
                distances = results['distances'][0]

                for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    # Convert distance to score (smaller distance -> higher score)
                    score = 1.0 / (1.0 + distance)

                    # Threshold filter
                    if score >= score_threshold:
                        relevant_docs.append({
                            'text': doc,
                            'score': score,
                            'distance': distance,
                            'source': metadata.get('source_file', 'Unknown'),
                            'type': metadata.get('chunk_type', 'N/A'),
                            'chunk_id': metadata.get('chunk_id', 0),
                            'char_count': metadata.get('char_count', 0),
                            'metadata': metadata,
                            'rank': i + 1
                        })

            logger.info(f"Search: '{query[:50]}...' - {len(relevant_docs)} relevant results")
            return relevant_docs

        except Exception as e:
            logger.error(f"Error in RAG search: {str(e)}")
            return []

    def prepare_context_for_claude(self,
                                query: str,
                                max_docs: int = 5,
                                max_context_length: int = 4000,
                                similarity_threshold: float = 0.01) -> Dict[str, Any]:
        """
        Prepare enriched context to send to Claude
        """
        try:
            # Retrieve relevant docs
            relevant_docs = self.search_relevant_docs(query, k=max_docs, score_threshold=similarity_threshold)

            # Format context
            if relevant_docs:
                formatted_context = RAGUtils.format_context_for_claude(
                    relevant_docs,
                    query,
                    max_context_length
                )

                return {
                    'success': True,
                    'enhanced_prompt': formatted_context,
                    'original_query': query,
                    'relevant_docs_count': len(relevant_docs),
                    'max_relevance_score': max(doc['score'] for doc in relevant_docs),
                    'sources': [doc['source'] for doc in relevant_docs],
                    'context_chunks': relevant_docs,
                    'rag_enabled': True
                }
            else:
                # Fallback without RAG context
                fallback_prompt = f"""
CONSULTA JURÍDICA: {query}

CONTEXTO: Nenhum documento relevante encontrado no banco de conhecimento.
Por favor, responda baseado no seu conhecimento jurídico geral.

RESPOSTA:
"""
                return {
                    'success': True,
                    'enhanced_prompt': fallback_prompt,
                    'original_query': query,
                    'relevant_docs_count': 0,
                    'max_relevance_score': 0,
                    'sources': [],
                    'rag_enabled': False,
                    'fallback_reason': 'Nenhum documento relevante encontrado'
                }

        except Exception as e:
            error_msg = f"Error preparing context: {str(e)}"
            logger.error(error_msg)

            # Fallback on error
            return {
                'success': False,
                'enhanced_prompt': f"CONSULTA: {query}\n\nERRO RAG: {error_msg}",
                'original_query': query,
                'relevant_docs_count': 0,
                'max_relevance_score': 0,
                'sources': [],
                'rag_enabled': False,
                'error': error_msg
            }

    def get_collection_stats(self) -> Dict[str, Any]:
        """Return collection statistics"""
        if not self.rag_available or not self.collection:
            return {
                'rag_available': False,
                'total_chunks': 0,
                'error': 'RAG not available'
            }

        try:
            count = self.collection.count()

            # Sample size for inspection
            sample_size = min(10, count) if count > 0 else 0

            stats = {
                'rag_available': True,
                'total_chunks': count,
                'collection_name': self.collection_name,
                'db_path': str(self.chroma_db_path),
                'embedding_model': self.embedding_model_name,
                'sample_size': sample_size
            }

            if sample_size > 0:
                # Peek sample for insights
                sample = self.collection.peek(limit=sample_size)
                if sample['metadatas']:
                    sources = set()
                    chunk_types = {}

                    for metadata in sample['metadatas']:
                        if 'source_file' in metadata:
                            sources.add(metadata['source_file'])

                        chunk_type = metadata.get('chunk_type', 'unknown')
                        chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

                    stats.update({
                        'unique_sources': len(sources),
                        'source_files': list(sources),
                        'chunk_type_distribution': chunk_types
                    })

            return stats

        except Exception as e:
            return {
                'rag_available': False,
                'total_chunks': 0,
                'error': str(e)
            }

    def clear_collection(self) -> Dict[str, Any]:
        """Delete all documents in the collection"""
        if not self.rag_available:
            return {
                'success': False,
                'error': 'RAG not available'
            }

        try:
            # Get all IDs
            all_data = self.collection.get()

            if all_data['ids']:
                # Remove all documents
                self.collection.delete(ids=all_data['ids'])
                # PersistentClient persists automatically

                logger.info(f"Collection '{self.collection_name}' cleared - {len(all_data['ids'])} chunks removed")

                return {
                    'success': True,
                    'removed_chunks': len(all_data['ids'])
                }
            else:
                return {
                    'success': True,
                    'removed_chunks': 0,
                    'message': 'Collection was already empty'
                }

        except Exception as e:
            error_msg = f"Error clearing collection: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def is_available(self) -> bool:
        """Check if RAG is available"""
        return self.rag_available
    
    def get_dependencies_status(self) -> Dict[str, bool]:
        """Return dependency status"""
        return {
            'chromadb': CHROMADB_AVAILABLE,
            'sentence_transformers': SENTENCE_TRANSFORMERS_AVAILABLE,
            'document_processor': True,
            'rag_manager': self.rag_available
        }
