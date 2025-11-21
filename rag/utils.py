"""
RAG Utils - Utilities for RAG processing
Helper functions for chunking, validation, and formatting
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class RAGUtils:
	"""Utilities for legal RAG processing"""
	
	# Legal patterns for intelligent chunking
	JURIDICAL_SEPARATORS = [
		r'\bArt\.?\s*\d+',           # Articles (Art. 1, Art 2)
		r'\bArtigo\s+\d+',          # Article 1, Article 2
		r'\bSeção\s+[IVX]+',        # Section I, Section II
		r'\bCapítulo\s+[IVX]+',     # Chapter I, Chapter II
		r'\b§\s*\d+',               # Paragraphs (§ 1, § 2)
		r'\bInciso\s+[IVX]+',       # Clause I, Clause II
		r'\bAlínea\s+[a-z]\)',      # Letter a), Letter b)
		r'\n\n+',                   # Paragraph breaks
	]
	
	SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt'}
	
	@staticmethod
	def validate_file_path(file_path: str) -> Tuple[bool, str]:
		"""
		Validate if file exists and is supported
		
		Args:
		    file_path: Path to file
		
		Returns:
		    Tuple[bool, str]: (is_valid, message)
		"""
		try:
			path = Path(file_path)
			
			if not path.exists():
				return False, f"File not found: {file_path}"
			
			if path.suffix.lower() not in RAGUtils.SUPPORTED_EXTENSIONS:
				return False, f"Unsupported extension: {path.suffix}"
			
			if path.stat().st_size == 0:
				return False, f"Empty file: {file_path}"
			
			return True, "Valid file"
			
		except Exception as e:
			return False, f"Error validating file: {str(e)}"
	
	@staticmethod
	def validate_file(file_path: str) -> bool:
		"""
		Simplified validation for compatibility.
		"""
		is_valid, _ = RAGUtils.validate_file_path(file_path)
		return is_valid
	
	@staticmethod
	def intelligent_chunk_text(text: str, 
	                         max_chunk_size: int = 1000,
	                         overlap_size: int = 200) -> List[Dict[str, Any]]:
		"""
		Intelligent chunking for legal documents
		"""
		chunks = []
		
		try:
			# First, try splitting by legal separators
			juridical_chunks = RAGUtils._split_by_juridical_patterns(text)
			
			# If none found, fall back to paragraph splitting
			if len(juridical_chunks) <= 1:
				juridical_chunks = text.split('\n\n')
			
			current_chunk = ""
			chunk_index = 0
			
			for section in juridical_chunks:
				section = section.strip()
				if not section:
					continue
				
				# If adding this section doesn't exceed the limit
				if len(current_chunk + section) <= max_chunk_size:
					current_chunk += ("\n\n" if current_chunk else "") + section
				else:
					# Save current chunk if not empty
					if current_chunk:
						chunks.append({
							'text': current_chunk.strip(),
							'chunk_id': chunk_index,
							'char_count': len(current_chunk),
							'type': RAGUtils._identify_chunk_type(current_chunk)
						})
						chunk_index += 1
					
					# Start new chunk
					current_chunk = section
			
			# Add last chunk
			if current_chunk:
				chunks.append({
					'text': current_chunk.strip(),
					'chunk_id': chunk_index,
					'char_count': len(current_chunk),
					'type': RAGUtils._identify_chunk_type(current_chunk)
				})
			
			# Add overlap between chunks
			chunks = RAGUtils._add_overlap(chunks, overlap_size)
			
			logger.info(f"Text split into {len(chunks)} chunks")
			return chunks
			
		except Exception as e:
			logger.error(f"Chunking error: {str(e)}")
			# Fallback: simple chunking
			return RAGUtils._simple_chunk_fallback(text, max_chunk_size)
	
	@staticmethod
	def chunk_juridical_document(text: str, 
	                           doc_type: str = "lei",
	                           chunk_size: int = 500,
	                           chunk_overlap: int = 50) -> List[Dict]:
		"""
		Apply intelligent legal chunking to text.
		Interface compatible with tests.
		"""
		chunks = RAGUtils.intelligent_chunk_text(
			text=text,
			max_chunk_size=chunk_size,
			overlap_size=chunk_overlap
		)
		
		# Add document type to metadata
		for chunk in chunks:
			if 'metadata' not in chunk:
				chunk['metadata'] = {}
			chunk['metadata']['doc_type'] = doc_type
			
		return chunks
	
	@staticmethod
	def _split_by_juridical_patterns(text: str) -> List[str]:
		"""Split text using legal patterns"""
		# Combine all patterns into one regex
		pattern = '|'.join(f'({pattern})' for pattern in RAGUtils.JURIDICAL_SEPARATORS)
		
		# Find all separator positions
		matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
		
		if not matches:
			return [text]
		
		chunks = []
		start = 0
		
		for match in matches:
			# Add text before the separator
			if match.start() > start:
				chunk = text[start:match.start()].strip()
				if chunk:
					chunks.append(chunk)
			
			start = match.start()
		
		# Add last chunk
		final_chunk = text[start:].strip()
		if final_chunk:
			chunks.append(final_chunk)
		
		return chunks
	
	@staticmethod
	def _identify_chunk_type(text: str) -> str:
		"""Identify chunk type based on content"""
		text_lower = text.lower()
		
		if re.search(r'\bart\.?\s*\d+', text_lower):
			return 'article'
		elif re.search(r'\bseção\s+[ivx]+', text_lower):
			return 'section'
		elif re.search(r'\bcapítulo\s+[ivx]+', text_lower):
			return 'chapter'
		elif re.search(r'\b§\s*\d+', text_lower):
			return 'paragraph'
		elif re.search(r'\binciso\s+[ivx]+', text_lower):
			return 'clause'
		else:
			return 'plain_paragraph'
	
	@staticmethod
	def _add_overlap(chunks: List[Dict], overlap_size: int) -> List[Dict]:
		"""Add overlap between consecutive chunks"""
		if len(chunks) <= 1 or overlap_size <= 0:
			return chunks
		
		overlapped_chunks = []
		
		for i, chunk in enumerate(chunks):
			new_chunk = chunk.copy()
			
			# Add overlap from previous chunk
			if i > 0:
				prev_text = chunks[i-1]['text']
				overlap_text = prev_text[-overlap_size:] if len(prev_text) > overlap_size else prev_text
				new_chunk['text'] = overlap_text + "\n\n" + new_chunk['text']
			
			# Add overlap from next chunk
			if i < len(chunks) - 1:
				next_text = chunks[i+1]['text']
				overlap_text = next_text[:overlap_size] if len(next_text) > overlap_size else next_text
				new_chunk['text'] = new_chunk['text'] + "\n\n" + overlap_text
			
			overlapped_chunks.append(new_chunk)
		
		return overlapped_chunks
	
	@staticmethod
	def _simple_chunk_fallback(text: str, max_size: int) -> List[Dict]:
		"""Simple chunking fallback in case of error"""
		chunks = []
		words = text.split()
		current_chunk = []
		current_size = 0
		chunk_index = 0
		
		for word in words:
			if current_size + len(word) + 1 > max_size and current_chunk:
				chunk_text = ' '.join(current_chunk)
				chunks.append({
					'text': chunk_text,
					'chunk_id': chunk_index,
					'char_count': len(chunk_text),
					'type': 'fallback'
				})
				chunk_index += 1
				current_chunk = [word]
				current_size = len(word)
			else:
				current_chunk.append(word)
				current_size += len(word) + 1
		
		# Add last chunk
		if current_chunk:
			chunk_text = ' '.join(current_chunk)
			chunks.append({
				'text': chunk_text,
				'chunk_id': chunk_index,
				'char_count': len(chunk_text),
				'type': 'fallback'
			})
		
		return chunks
	
	@staticmethod
	def format_context_for_claude(relevant_docs: List[Dict], 
	                            query: str,
	                            max_context_length: int = 4000) -> str:
		"""
		Format context optimized for Claude AI
		"""
		if not relevant_docs:
			return f"""
LEGAL QUERY: {query}

CONTEXT: No relevant documents found in the knowledge base.
Please answer based on your general legal knowledge.
"""
		
		# Sort by relevance (score)
		sorted_docs = sorted(relevant_docs, 
					   key=lambda x: x.get('score', 0), 
					   reverse=True)
		
		context_parts = [
			"=== RELEVANT LEGAL CONTEXT ===\n"
		]
		
		current_length = len(context_parts[0])
		doc_count = 0
		
		for doc in sorted_docs:
			# Format each document
			doc_text = f"""
DOCUMENT {doc_count + 1}: {doc.get('source', 'Unknown source')}
Relevance: {doc.get('score', 0):.2f}
Type: {doc.get('type', 'N/A')}

CONTENT:
{doc.get('text', 'Text not available')}

---
"""
			
			# Check if it fits the limit
			if current_length + len(doc_text) > max_context_length:
				if doc_count == 0:  # Ensure at least one document
					# Truncate the first doc to fit
					available_space = max_context_length - current_length - 100
					if available_space > 0:
						truncated_text = doc.get('text', '')[:available_space] + "...[TRUNCATED]"
						doc_text = f"""
DOCUMENT 1: {doc.get('source', 'Unknown source')}
Relevance: {doc.get('score', 0):.2f}
Type: {doc.get('type', 'N/A')}

CONTENT:
{truncated_text}

---
"""
						context_parts.append(doc_text)
						doc_count += 1
				break
			
			context_parts.append(doc_text)
			current_length += len(doc_text)
			doc_count += 1
		
		# Final instructions
		context_parts.append(f"""
=== QUERY ===
{query}

=== INSTRUCTIONS ===
1. Analyze the documents above
2. Cite specific relevant sources
3. If applicable, mention specific articles, paragraphs, or sections
4. Provide a legally grounded answer based on the context
5. If context is insufficient, say so clearly

ANSWER:
""")
		
		return ''.join(context_parts)
	
	@staticmethod
	def extract_metadata_from_path(file_path: str) -> Dict[str, Any]:
		"""Extract simple metadata from the file path"""
		path = Path(file_path)
		
		return {
			'filename': path.name,
			'extension': path.suffix.lower(),
			'size_bytes': path.stat().st_size if path.exists() else 0,
			'absolute_path': str(path.absolute()),
			'parent_directory': path.parent.name
		}
	
	@staticmethod
	def clean_text(text: str) -> str:
		"""Clean and normalize text"""
		if not text:
			return ""
		
		# Remove unnecessary control characters
		text = re.sub(r'\x00-\x1f\x7f-\x9f', '', text)  # Remove control chars
		
		# Normalize whitespace
		text = re.sub(r'\s+', ' ', text)
		
		# Trim
		text = text.strip()
		
		return text
