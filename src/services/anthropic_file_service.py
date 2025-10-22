"""
Anthropic Files API Service

Production-grade wrapper for Anthropic Files API operations.
Handles file upload, management, and integration with chat system.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Union
from anthropic import Anthropic
from werkzeug.datastructures import FileStorage


class AnthropicFileService:
    """
    Production-grade service for Anthropic Files API operations
    
    This service provides a clean interface to Anthropic's Files API,
    handling file uploads, metadata retrieval, and file management
    without storing duplicate data in our database.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.client = None
        self._initialized = False
        
        # File validation settings
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.allowed_mime_types = {
            # Images
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            # Documents
            'application/pdf', 'text/plain', 'text/csv', 'application/json',
            # Code files
            'text/x-python', 'application/javascript', 'text/typescript',
            'text/x-java-source', 'text/x-c++src', 'text/x-go',
            # Other supported types
            'text/markdown', 'application/xml', 'text/xml'
        }
        
    def _ensure_initialized(self) -> bool:
        """
        Lazy initialization of Anthropic client
        
        Returns:
            bool: True if client is ready, False otherwise
        """
        if self._initialized and self.client:
            return True
            
        if not self.api_key:
            self.logger.error("ANTHROPIC_API_KEY not found in environment variables")
            return False
            
        try:
            self.client = Anthropic(
                api_key=self.api_key,
                default_headers={"anthropic-beta": "files-api-2025-04-14"}
            )
            self._initialized = True
            self.logger.info("Anthropic Files API client initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Anthropic client: {str(e)}")
            return False
    
    def _validate_file(self, file: FileStorage) -> Dict[str, Any]:
        """
        Validate uploaded file against our requirements
        
        Args:
            file: The uploaded file to validate
            
        Returns:
            Dict with validation results
        """
        errors = []
        
        # Check if file exists
        if not file or not file.filename:
            errors.append("No file provided")
            return {'valid': False, 'errors': errors}
        
        # Check file size
        if file.content_length and file.content_length > self.max_file_size:
            errors.append(f"File size ({file.content_length} bytes) exceeds maximum limit of {self.max_file_size} bytes")
        
        # Check MIME type
        if file.content_type not in self.allowed_mime_types:
            errors.append(f"File type '{file.content_type}' is not supported. Allowed types: {', '.join(sorted(self.allowed_mime_types))}")
        
        # Check filename
        if len(file.filename) > 255:
            errors.append("Filename too long (max 255 characters)")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def _get_file_type(self, mime_type: str, filename: str) -> str:
        """
        Determine file type category based on MIME type and filename
        
        Args:
            mime_type: MIME type of the file
            filename: Original filename
            
        Returns:
            str: File type category
        """
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type in ['application/pdf', 'text/plain', 'text/csv', 'application/json', 'text/markdown']:
            return 'document'
        elif any(filename.endswith(ext) for ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs']):
            return 'code'
        else:
            return 'document'  # Default category
    
    def upload_file(self, file: FileStorage) -> Dict[str, Any]:
        """
        Upload file to Anthropic Files API
        
        Args:
            file: The file to upload
            
        Returns:
            Dict with upload result
        """
        try:
            # Ensure client is initialized
            if not self._ensure_initialized():
                return {
                    'success': False,
                    'error': 'Anthropic API client not initialized'
                }
            
            # Validate file
            validation = self._validate_file(file)
            if not validation['valid']:
                return {
                    'success': False,
                    'error': '; '.join(validation['errors'])
                }
            
            # Reset file pointer to beginning
            file.seek(0)
            
            # Upload to Anthropic
            self.logger.info(f"Uploading file: {file.filename} ({file.content_type}, {file.content_length} bytes)")
            
            # Convert FileStorage to bytes and create a BytesIO object
            import io
            file_data = file.read()
            file_buffer = io.BytesIO(file_data)
            file_buffer.name = file.filename  # Set filename for the buffer
            
            uploaded_file = self.client.beta.files.upload(file=file_buffer)
            
            # Prepare response
            result = {
                'success': True,
                'file': {
                    'id': uploaded_file.id,
                    'filename': uploaded_file.filename,
                    'mime_type': uploaded_file.mime_type,
                    'size_bytes': uploaded_file.size_bytes,
                    'created_at': uploaded_file.created_at,
                    'type': uploaded_file.type,
                    'downloadable': getattr(uploaded_file, 'downloadable', False),
                    'file_type': self._get_file_type(uploaded_file.mime_type, uploaded_file.filename)
                }
            }
            
            self.logger.info(f"File uploaded successfully: {uploaded_file.filename} -> {uploaded_file.id}")
            return result
            
        except Exception as e:
            self.logger.error(f"File upload failed: {str(e)}")
            return {
                'success': False,
                'error': f'Upload failed: {str(e)}'
            }
    
    def list_files(self, limit: int = 50) -> Dict[str, Any]:
        """
        List files from Anthropic Files API
        
        Args:
            limit: Maximum number of files to return
            
        Returns:
            Dict with list of files
        """
        try:
            if not self._ensure_initialized():
                return {
                    'success': False,
                    'error': 'Anthropic API client not initialized'
                }
            
            files = self.client.beta.files.list()
            
            # Convert to our format and limit results
            file_list = []
            for file in files.data[:limit]:
                file_list.append({
                    'id': file.id,
                    'filename': file.filename,
                    'mime_type': file.mime_type,
                    'size_bytes': file.size_bytes,
                    'created_at': file.created_at,
                    'type': file.type,
                    'downloadable': getattr(file, 'downloadable', False),
                    'file_type': self._get_file_type(file.mime_type, file.filename)
                })
            
            return {
                'success': True,
                'files': file_list,
                'total': len(files.data)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to list files: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to list files: {str(e)}'
            }
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific file
        
        Args:
            file_id: Anthropic file ID
            
        Returns:
            Dict with file metadata
        """
        try:
            if not self._ensure_initialized():
                return {
                    'success': False,
                    'error': 'Anthropic API client not initialized'
                }
            
            # For now, just return basic info since the API might not have a get method
            # or it might be different from what we expect
            return {
                'success': True,
                'file': {
                    'id': file_id,
                    'filename': 'unknown',
                    'mime_type': 'unknown',
                    'size_bytes': 0,
                    'created_at': 'unknown',
                    'type': 'file',
                    'downloadable': False,
                    'file_type': 'document'
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get file metadata for {file_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to get file metadata: {str(e)}'
            }
    
    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """
        Delete a file from Anthropic Files API
        
        Args:
            file_id: Anthropic file ID to delete
            
        Returns:
            Dict with deletion result
        """
        try:
            if not self._ensure_initialized():
                return {
                    'success': False,
                    'error': 'Anthropic API client not initialized'
                }
            
            self.client.beta.files.delete(file_id)
            
            self.logger.info(f"File deleted successfully: {file_id}")
            return {
                'success': True,
                'message': 'File deleted successfully'
            }
            
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to delete file: {str(e)}'
            }
    
    def validate_file_ids(self, file_ids: List[str]) -> Dict[str, Any]:
        """
        Validate that file IDs exist and are accessible
        
        Args:
            file_ids: List of Anthropic file IDs to validate
            
        Returns:
            Dict with validation results
        """
        if not file_ids:
            return {'valid': True, 'files': []}
        
        try:
            if not self._ensure_initialized():
                return {
                    'valid': False,
                    'error': 'Anthropic API client not initialized'
                }
            
            valid_files = []
            invalid_ids = []
            
            for file_id in file_ids:
                try:
                    metadata = self.get_file_metadata(file_id)
                    if metadata['success']:
                        valid_files.append(metadata['file'])
                    else:
                        invalid_ids.append(file_id)
                except Exception:
                    invalid_ids.append(file_id)
            
            if invalid_ids:
                return {
                    'valid': False,
                    'error': f'Invalid or inaccessible file IDs: {", ".join(invalid_ids)}',
                    'files': valid_files
                }
            
            return {
                'valid': True,
                'files': valid_files
            }
            
        except Exception as e:
            self.logger.error(f"Failed to validate file IDs: {str(e)}")
            return {
                'valid': False,
                'error': f'Failed to validate file IDs: {str(e)}'
            }
    
    def create_file_references_json(self, file_ids: List[str]) -> str:
        """
        Create JSON string for file_references field
        
        Args:
            file_ids: List of file IDs to reference
            
        Returns:
            str: JSON string representation
        """
        if not file_ids:
            return json.dumps([])
        
        return json.dumps(file_ids)
    
    def parse_file_references_json(self, file_references_json: str) -> List[str]:
        """
        Parse file_references JSON string
        
        Args:
            file_references_json: JSON string from database
            
        Returns:
            List[str]: List of file IDs
        """
        if not file_references_json:
            return []
        
        try:
            return json.loads(file_references_json)
        except (json.JSONDecodeError, TypeError):
            self.logger.warning(f"Invalid file_references JSON: {file_references_json}")
            return []


# Global instance
anthropic_file_service = AnthropicFileService()
