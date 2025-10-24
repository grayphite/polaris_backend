"""
RAG Configuration Management
Single source of truth for all RAG settings

This file contains all configuration parameters for the RAG (Retrieval-Augmented Generation) system.
You can override any setting using environment variables.

Environment Variables:
- RAG_SCORE_THRESHOLD: Similarity threshold for document search (0.01-0.5)
- RAG_MAX_RESULTS: Maximum search results to return (1-20)
- RAG_MAX_DOCS: Maximum documents to include in context (1-10)
- CHROMA_CONNECTION_TYPE: Database connection type ("local" or "cloud")
- CHROMA_API_KEY: API key for TryChroma authentication
- CHROMA_TENANT: Tenant ID for TryChroma (e.g., '50038ca8-6cf8-40f2-8dcd-53598fdeb080')
- CHROMA_DATABASE: Database name for TryChroma (e.g., 'polaris')
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class RAGSearchConfig:
    """
    Configuration for RAG search parameters
    
    These settings control how the RAG system searches for relevant documents
    and prepares context for the AI model.
    """
    
    # Search thresholds - Controls document relevance filtering
    default_score_threshold: float = 0.01  # Main similarity threshold (0.01=more results, 0.1=fewer but better)
    min_score_threshold: float = 0.01      # Minimum allowed threshold (prevents too low values)
    max_score_threshold: float = 0.5       # Maximum allowed threshold (prevents too high values)
    
    # Search limits - Controls how many documents to retrieve
    default_max_results: int = 5           # Maximum number of search results to return
    min_max_results: int = 1              # Minimum allowed results (performance limit)
    max_max_results: int = 20             # Maximum allowed results (performance limit)
    
    # Context preparation - Controls how context is prepared for AI
    default_max_docs: int = 3             # Maximum documents to include in context for Claude
    default_max_context_length: int = 4000 # Maximum characters in enhanced prompt sent to Claude


@dataclass
class RAGDocumentConfig:
    """
    Configuration for document processing
    
    These settings control how documents are processed, chunked, and stored
    in the vector database for RAG functionality.
    """
    
    # Chunking settings - Controls how documents are split into chunks
    default_chunk_size: int = 1000          # Size of text chunks (200=small, 2000=large)
    default_chunk_overlap: int = 200        # Overlap between chunks for better context
    
    # File processing - Controls file handling and limits
    max_file_size_mb: int = 500            # Maximum file size in MB before processing (production grade)
    supported_extensions: list = field(default_factory=lambda: [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt"])  # File types that can be processed by RAG
    max_documents_per_batch: int = 50      # Maximum documents to process in one batch (increased for production)
    
    # Processing limits - Controls system resource usage
    max_total_chunks: int = 100000         # Maximum total chunks allowed in database (production grade)
    max_chunks_per_document: int = 5000    # Maximum chunks per single document (prevents memory issues)


@dataclass
class RAGDatabaseConfig:
    """
    Configuration for database settings
    
    These settings control the vector database (ChromaDB) connection,
    embedding models, and performance parameters.
    """
    
    # ChromaDB settings - Controls local database storage
    default_db_path: str = "./chroma_db"                    # Path where ChromaDB stores vector data
    default_collection_name: str = "juridical_documents"     # Name of the document collection in ChromaDB
    
    # Connection settings - Controls database connection type
    connection_type: str = "local"  # "local" for file-based, "cloud" for remote ChromaDB (TryChroma, etc.)
    cloud_config: dict = field(default_factory=lambda: {    # TryChroma configuration
        "api_key": None,                                     # API key for TryChroma authentication
        "tenant": None,                                      # Tenant ID for TryChroma (e.g., '50038ca8-6cf8-40f2-8dcd-53598fdeb080')
        "database": None,                                    # Database name for TryChroma (e.g., 'polaris')
    })
    
    # Embedding model - Controls AI model for text-to-vector conversion
    default_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # AI model for converting text to vectors (multilingual support)
    fallback_embedding_model: str = "all-MiniLM-L6-v2"      # Backup embedding model if main model fails
    
    # Performance settings - Controls database performance
    batch_size: int = 500                                    # Number of documents to process in one batch (reduced for TryChroma compatibility)
    persist_interval: int = 1000                             # How often to save data to disk
    max_batch_size: int = 500                                # Maximum batch size for ChromaDB operations
    chunk_batch_size: int = 500                              # Maximum chunks to process in one batch


@dataclass
class RAGAPIConfig:
    """
    Configuration for API endpoints
    
    These settings control API rate limiting, request validation,
    and response timeouts for the RAG system.
    """
    
    # Rate limiting - Controls API usage limits
    default_rate_limit: int = 100            # Maximum API requests per hour per user
    max_rate_limit: int = 1000              # Maximum allowed rate limit (admin override)
    
    # Request limits - Controls input validation
    max_prompt_length: int = 15000          # Maximum characters in user prompts
    min_prompt_length: int = 10             # Minimum characters in user prompts
    
    # Response settings - Controls API response behavior
    default_timeout: int = 30               # Request timeout in seconds
    max_timeout: int = 120                  # Maximum allowed timeout (admin override)


@dataclass
class RAGConfig:
    """
    Main RAG configuration container
    
    This is the top-level configuration class that contains all RAG settings.
    It combines search, document, database, and API configurations.
    """
    
    # Configuration sections - Each section controls a specific aspect of RAG
    search: RAGSearchConfig = field(default_factory=RAGSearchConfig)      # Document search and retrieval settings
    document: RAGDocumentConfig = field(default_factory=RAGDocumentConfig)  # Document processing settings
    database: RAGDatabaseConfig = field(default_factory=RAGDatabaseConfig)  # Database connection and storage settings
    api: RAGAPIConfig = field(default_factory=RAGAPIConfig)              # API endpoint settings
    
    # Environment settings - Controls system behavior
    environment: str = "development"  # Current environment (development/staging/production)
    debug_mode: bool = False          # Enable debug logging (true/false)
    log_level: str = "INFO"           # Logging level (DEBUG/INFO/WARNING/ERROR)


class RAGConfigManager:
    """
    Professional configuration manager for RAG system
    
    This class handles loading configuration from defaults and environment variables.
    It provides a single interface for accessing all RAG settings.
    """
    
    def __init__(self):
        """Initialize configuration manager"""
        self.config = self._load_config()
        
    def _load_config(self) -> RAGConfig:
        """
        Load configuration with environment variable overrides
        
        This method loads the default configuration and then overrides
        any values that are set via environment variables.
        """
        
        # Start with defaults from the dataclass definitions
        config = RAGConfig()
        
        # Override search settings with environment variables
        config.search.default_score_threshold = float(
            os.getenv('RAG_SCORE_THRESHOLD', config.search.default_score_threshold)
        )
        config.search.default_max_results = int(
            os.getenv('RAG_MAX_RESULTS', config.search.default_max_results)
        )
        config.search.default_max_docs = int(
            os.getenv('RAG_MAX_DOCS', config.search.default_max_docs)
        )
        
        # Override database connection settings with environment variables
        config.database.connection_type = os.getenv('CHROMA_CONNECTION_TYPE', config.database.connection_type)
        
        # TryChroma environment variables
        if os.getenv('CHROMA_API_KEY'):
            config.database.cloud_config['api_key'] = os.getenv('CHROMA_API_KEY')
        if os.getenv('CHROMA_TENANT'):
            config.database.cloud_config['tenant'] = os.getenv('CHROMA_TENANT')
        if os.getenv('CHROMA_DATABASE'):
            config.database.cloud_config['database'] = os.getenv('CHROMA_DATABASE')
        
        # Override environment settings with environment variables
        config.environment = os.getenv('RAG_ENVIRONMENT', config.environment)
        config.debug_mode = os.getenv('RAG_DEBUG', 'false').lower() == 'true'
        config.log_level = os.getenv('RAG_LOG_LEVEL', config.log_level)
        
        return config
    
    def get_config(self) -> RAGConfig:
        """
        Get current configuration
        
        Returns:
            RAGConfig: The current configuration object with all settings
        """
        return self.config
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration values programmatically
        
        Args:
            **kwargs: Configuration key-value pairs to update
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                logger.warning(f"Unknown configuration key: {key}")
    
    def show_config(self) -> None:
        """
        Display current configuration in a human-readable format
        
        This method prints all current configuration settings to the console,
        making it easy to see what values are currently active.
        """
        print("🔧 RAG Configuration:")
        print(f"  Environment: {self.config.environment}")
        print(f"  Debug Mode: {self.config.debug_mode}")
        print(f"  Log Level: {self.config.log_level}")
        print()
        print("📊 Search Settings:")
        print(f"  Score Threshold: {self.config.search.default_score_threshold}")
        print(f"  Max Results: {self.config.search.default_max_results}")
        print(f"  Max Docs: {self.config.search.default_max_docs}")
        print()
        print("🗄️ Database Settings:")
        print(f"  Connection Type: {self.config.database.connection_type}")
        print(f"  DB Path: {self.config.database.default_db_path}")
        print(f"  Collection: {self.config.database.default_collection_name}")
        if self.config.database.connection_type == "cloud":
            print("  TryChroma Configuration:")
            print(f"    API Key: {'Set' if self.config.database.cloud_config.get('api_key') else 'Not set'}")
            print(f"    Tenant: {self.config.database.cloud_config.get('tenant', 'Not set')}")
            print(f"    Database: {self.config.database.cloud_config.get('database', 'Not set')}")


# Global configuration instance - Singleton pattern for configuration management
_config_manager = None

def get_rag_config_values() -> RAGConfig:
    """
    Get RAG configuration values
    
    This is the main function to access RAG configuration throughout the application.
    It uses a singleton pattern to ensure consistent configuration across the system.
    
    Returns:
        RAGConfig: The current configuration object with all settings
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = RAGConfigManager()
    return _config_manager.get_config()

def show_rag_config() -> None:
    """
    Display current RAG configuration
    
    This function prints all current configuration settings to the console,
    making it easy to debug configuration issues or verify settings.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = RAGConfigManager()
    _config_manager.show_config()
