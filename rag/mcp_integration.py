"""
MCP Integration - Bridge between RAG and existing MCP system
Safe integration that does not modify original MCP code
"""

import logging
from typing import Dict, Any, Optional

try:
	from .rag_manager import JuridicalRAGManager
	RAG_MANAGER_AVAILABLE = True
except ImportError:
	RAG_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)


class MCPRAGIntegration:
	"""
	Bridge between RAG system and existing MCP
	Implements adapter pattern for safe integration
	"""
	
	def __init__(self, rag_manager: Optional[JuridicalRAGManager] = None):
		"""
		Initialize MCP-RAG integration
		
		Args:
		    rag_manager: Optional RAG Manager instance
		"""
		self.rag_manager = rag_manager
		self.rag_enabled = rag_manager is not None and rag_manager.is_available()
		
		if self.rag_enabled:
			logger.info("MCP-RAG Integration enabled")
		else:
			logger.warning("MCP-RAG Integration in fallback mode")
	
	def handle_rag_query(self, 
	                   query: str,
	                   enable_rag: bool = True,
	                   max_docs: int = 5,
	                   context_length: int = 4000,
	                   similarity_threshold: float = 0.01) -> Dict[str, Any]:
		"""
		Process query with RAG context enrichment
		
		Args:
		    query: Original legal query
		    enable_rag: Whether to use RAG (allows disabling)
		    max_docs: Max documents for context
		    context_length: Max context length
		
		Returns:
		    Dict with enriched prompt and metadata
		"""
		try:
			# If RAG not available or disabled, use fallback
			if not self.rag_enabled or not enable_rag:
				return self._fallback_response(query, "RAG disabled or unavailable")
			
			# Use RAG to enrich context
			rag_result = self.rag_manager.prepare_context_for_claude(
				query=query,
				max_docs=max_docs,
				max_context_length=context_length,
				similarity_threshold=similarity_threshold
			)
			
			if rag_result['success']:
				return {
					'enhanced_prompt': rag_result['enhanced_prompt'],
					'original_query': query,
					'rag_metadata': {
						'docs_found': rag_result['relevant_docs_count'],
						'max_score': rag_result.get('max_relevance_score', 0),
						'sources': rag_result.get('sources', []),
						'rag_enabled': rag_result['rag_enabled'],
						'context_chunks': rag_result.get('context_chunks', [])
					},
					'context_chunks': rag_result.get('context_chunks', []),
					'mcp_compatible': True,
					'processing_mode': 'rag_enhanced'
				}
			else:
				# RAG failed, use fallback
				return self._fallback_response(
					query, 
					f"RAG error: {rag_result.get('error', 'Unknown error')}"
				)
				
		except Exception as e:
			logger.error(f"Error in MCP-RAG integration: {str(e)}")
			return self._fallback_response(query, f"Integration error: {str(e)}")
	
	def juridical_query(self, 
	                  query: str,
	                  max_chunks: int = 5,
	                  similarity_threshold: float = 0.05) -> Dict[str, Any]:
		"""
		Alias for handle_rag_query with parameters specific to legal queries.
		Keeps compatibility with expected interface.
		"""
		result = self.handle_rag_query(
			query=query,
			enable_rag=True,
			max_docs=max_chunks,
			context_length=4000,
			similarity_threshold=similarity_threshold
		)
		
		# Adapt response to expected interface
		if result.get('processing_mode') == 'fallback':
			return {
				'success': False,
				'response': result.get('enhanced_prompt', ''),
				'error': result.get('rag_metadata', {}).get('fallback_reason', 'RAG unavailable'),
				'sources': [],
				'context_chunks': []
			}
		else:
			return {
				'success': True,
				'response': result.get('enhanced_prompt', ''),
				'sources': result.get('rag_metadata', {}).get('sources', []),
				'context_chunks': result.get('rag_metadata', {}).get('context_chunks', [])
			}
	
	def _fallback_response(self, query: str, reason: str) -> Dict[str, Any]:
		"""
		Fallback response when RAG is not available.
		Keeps compatibility with original MCP.
		"""
		fallback_prompt = f"""
LEGAL QUERY: {query}

MODE: Knowledge-base analysis
NOTE: {reason}

Please answer based on general legal knowledge when specific context is unavailable.

ANSWER:
"""
		
		return {
			'enhanced_prompt': fallback_prompt,
			'original_query': query,
			'rag_metadata': {
				'docs_found': 0,
				'max_score': 0,
				'sources': [],
				'rag_enabled': False,
				'fallback_reason': reason
			},
			'mcp_compatible': True,
			'processing_mode': 'fallback'
		}
	
	def add_documents_to_rag(self, file_paths: list) -> Dict[str, Any]:
		"""
		Add documents to the RAG system
		"""
		if not self.rag_enabled:
			return {
				'success': False,
				'error': 'RAG is not available',
				'suggestion': 'Install dependencies: pip install -r requirements_rag.txt'
			}
		
		try:
			result = self.rag_manager.add_documents(file_paths)
			
			# Add extra info for MCP integration
			result['mcp_integration'] = {
				'total_files_processed': result.get('processed_documents', 0),
				'ready_for_queries': result.get('success', False),
				'recommendation': ('Documents ready for RAG queries' 
				                 if result.get('success') 
				                 else 'Check processing errors')
			}
			
			return result
			
		except Exception as e:
			logger.error(f"Error adding documents via MCP: {str(e)}")
			return {
				'success': False,
				'error': str(e),
				'mcp_integration': {
					'total_files_processed': 0,
					'ready_for_queries': False,
					'recommendation': 'Check logs for error details'
				}
			}
	
	def get_rag_status(self) -> Dict[str, Any]:
		"""
		Return full RAG status (useful for debugging and monitoring)
		"""
		try:
			base_status = {
				'available': self.rag_enabled,
				'rag_integration_available': RAG_MANAGER_AVAILABLE,
				'rag_manager_initialized': self.rag_manager is not None,
				'rag_enabled': self.rag_enabled,
				'mcp_compatibility': True,
				'timestamp': '2024-01-15T10:00:00Z'
			}
			
			if self.rag_enabled and self.rag_manager:
				# Add detailed stats
				rag_stats = self.rag_manager.get_collection_stats()
				dependencies = self.rag_manager.get_dependencies_status()
				
				base_status.update({
					'collection_stats': rag_stats,
					'dependencies': dependencies,
					'recommendations': self._generate_recommendations(rag_stats, dependencies)
				})
			else:
				base_status.update({
					'collection_stats': {'total_chunks': 0, 'rag_available': False},
					'dependencies': {'chromadb': False, 'sentence_transformers': False},
					'reason': 'RAG dependencies not installed',
					'recommendations': [
						'Install dependencies: pip install -r requirements_rag.txt',
						'Restart the system after installation'
					]
				})
			
			return base_status
			
		except Exception as e:
			logger.error(f"Error getting RAG status: {str(e)}")
			return {
				'available': False,
				'rag_integration_available': False,
				'rag_manager_initialized': False,
				'rag_enabled': False,
				'mcp_compatibility': True,
				'error': str(e),
				'reason': f'Error accessing status: {str(e)}',
				'timestamp': '2024-01-15T10:00:00Z',
				'recommendations': ['Check system logs']
			}
	
	def _generate_recommendations(self, 
	                           rag_stats: Dict, 
	                           dependencies: Dict) -> list:
		"""Generate recommendations based on current status"""
		recommendations = []
		
		# Check dependencies
		missing_deps = [k for k, v in dependencies.items() if not v]
		if missing_deps:
			recommendations.append(f"Missing dependencies: {', '.join(missing_deps)}")
		
		# Check content
		total_chunks = rag_stats.get('total_chunks', 0)
		if total_chunks == 0:
			recommendations.append("Add documents to the RAG system for better context")
		elif total_chunks < 10:
			recommendations.append("Consider adding more documents for broader coverage")
		
		# Check sources
		unique_sources = rag_stats.get('unique_sources', 0)
		if unique_sources > 0 and unique_sources < 3:
			recommendations.append("Diversify sources for more comprehensive analyses")
		
		return recommendations if recommendations else ["RAG system operational"]
	
	def test_rag_integration(self, test_query: str = "integration test") -> Dict[str, Any]:
		"""
		End-to-end test for RAG integration. Useful for validation after setup.
		"""
		try:
			test_result = self.handle_rag_query(
				query=test_query,
				enable_rag=True,
				max_docs=3,
				context_length=1000
			)
			
			# Analyze test result
			test_successful = (
				test_result.get('mcp_compatible', False) and
				'enhanced_prompt' in test_result
			)
			
			return {
				'test_successful': test_successful,
				'processing_mode': test_result.get('processing_mode', 'unknown'),
				'rag_enabled': test_result.get('rag_metadata', {}).get('rag_enabled', False),
				'docs_found': test_result.get('rag_metadata', {}).get('docs_found', 0),
				'prompt_length': len(test_result.get('enhanced_prompt', '')),
				'test_query': test_query,
				'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
					'test', 0, '', 0, '', (), None
				)) if logger.handlers else 'N/A',
				'full_result': test_result
			}
			
		except Exception as e:
			return {
				'test_successful': False,
				'error': str(e),
				'test_query': test_query,
				'recommendation': 'Check RAG configuration and dependencies'
			}
	
	def clear_rag_data(self) -> Dict[str, Any]:
		"""Clear RAG data (useful for reprocessing)"""
		if not self.rag_enabled:
			return {
				'success': False,
				'error': 'RAG is not available'
			}
		
		try:
			result = self.rag_manager.clear_collection()
			
			# Add MCP context
			result['mcp_integration'] = {
				'action': 'clear_completed',
				'ready_for_new_documents': result.get('success', False),
				'recommendation': ('Ready to add new documents' 
				                 if result.get('success') 
				                 else 'Error clearing - check logs')
			}
			
			return result
			
		except Exception as e:
			return {
				'success': False,
				'error': str(e),
				'mcp_integration': {
					'action': 'clear_failed',
					'ready_for_new_documents': False,
					'recommendation': 'Check permissions and system logs'
				}
			}
	
	def is_available(self) -> bool:
		"""Check if integration is available"""
		return self.rag_enabled
	
	def is_rag_available(self) -> bool:
		"""Return True if RAG is fully available and functional."""
		return self.rag_enabled
	
	def get_supported_operations(self) -> list:
		"""List supported operations for the integration"""
		base_operations = [
			'handle_rag_query',
			'get_rag_status', 
			'test_rag_integration'
		]
		
		if self.rag_enabled:
			base_operations.extend([
				'add_documents_to_rag',
				'clear_rag_data'
			])
		
		return base_operations
