"""
RAG (Retrieval-Augmented Generation) Module for POLARIS
Search and context enrichment system for legal documents
"""

# Safe dependency checks for RAG
RAG_AVAILABLE = False
RAG_STATUS = "⚠️ Advanced RAG unavailable due to dependency conflicts"

# Try importing dependencies individually
try:
	import langchain  # noqa: F401
	LANGCHAIN_AVAILABLE = True
except ImportError:
	LANGCHAIN_AVAILABLE = False

try:
	import chromadb  # noqa: F401
	CHROMADB_AVAILABLE = True
except ImportError:
	CHROMADB_AVAILABLE = False

try:
	import sentence_transformers  # noqa: F401
	SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
	SENTENCE_TRANSFORMERS_AVAILABLE = False

# Status based on available dependencies
if CHROMADB_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE:
	RAG_AVAILABLE = True
	RAG_STATUS = "✅ RAG fully functional"
elif CHROMADB_AVAILABLE:
	RAG_AVAILABLE = True
	RAG_STATUS = "⚠️ RAG functional (without optimized sentence-transformers)"
else:
	rag_msg = (f"⚠️ RAG unavailable - chromadb: {CHROMADB_AVAILABLE}, "
	           f"sentence_transformers: {SENTENCE_TRANSFORMERS_AVAILABLE}")
	RAG_STATUS = rag_msg
	print(f"\n{RAG_STATUS}")
	print("To enable RAG, run: pip install -r requirements_rag.txt")

# Conditional imports to avoid dependency issues
try:
	from .document_processor import DocumentProcessor
	DOCUMENT_PROCESSOR_AVAILABLE = True
except ImportError as e:
	print(f"⚠️ DocumentProcessor unavailable: {e}")
	DOCUMENT_PROCESSOR_AVAILABLE = False
	DocumentProcessor = None

try:
	from .utils import RAGUtils
	RAG_UTILS_AVAILABLE = True
except ImportError as e:
	print(f"⚠️ RAGUtils unavailable: {e}")
	RAG_UTILS_AVAILABLE = False
	RAGUtils = None

# Temporarily commenting problematic imports
# from .rag_manager import JuridicalRAGManager
# from .mcp_integration import MCPRAGIntegration
JuridicalRAGManager = None
MCPRAGIntegration = None

__version__ = "1.0.0"
__all__ = [
	'RAG_AVAILABLE',
	'RAG_STATUS',
	'LANGCHAIN_AVAILABLE',
	'CHROMADB_AVAILABLE',
	'SENTENCE_TRANSFORMERS_AVAILABLE',
	'JuridicalRAGManager',
	'MCPRAGIntegration',
	'DocumentProcessor',
	'RAGUtils'
]
