"""
File Upload Routes

Production-grade file upload endpoints for Anthropic Files API integration.
Provides clean REST API for file management operations.
"""

from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from src.services.auth_service import auth_service
from src.services.anthropic_file_service import anthropic_file_service
from src.services.logging_service import logging_service, ActionType
import logging

# Create blueprint
file_upload_bp = Blueprint('file_upload', __name__)
logger = logging.getLogger(__name__)


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@file_upload_bp.route('/files/upload', methods=['POST'])
@auth_service.require_auth
def upload_file():
    """
    Upload a file to Anthropic Files API
    
    Expected form data:
    - file: The file to upload (multipart/form-data)
    
    Returns:
        JSON response with file metadata or error
    """
    try:
        current_user = get_current_user()
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Secure the filename
        file.filename = secure_filename(file.filename)
        
        # Upload file using service
        result = anthropic_file_service.upload_file(file)
        
        if result['success']:
            # Log the upload
            logging_service.audit(
                user_id=current_user.id,
                action_type=ActionType.CREATE,
                resource_type='file',
                resource_id=result['file']['id'],
                new_values=result['file'],
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                metadata={
                    'filename': result['file']['filename'],
                    'file_size': result['file']['size_bytes'],
                    'mime_type': result['file']['mime_type'],
                    'file_type': result['file']['file_type']
                }
            )
            
            logger.info(f"File uploaded by user {current_user.id}: {result['file']['filename']}")
            
            return jsonify({
                'success': True,
                'message': 'File uploaded successfully',
                'file': result['file']
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
            
    except Exception as e:
        logger.error(f"File upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@file_upload_bp.route('/files', methods=['GET'])
@auth_service.require_auth
def list_files():
    """
    List files from Anthropic Files API
    
    Query parameters:
    - limit: Maximum number of files to return (default: 50)
    
    Returns:
        JSON response with list of files
    """
    try:
        current_user = get_current_user()
        limit = request.args.get('limit', 50, type=int)
        
        # Validate limit
        if limit < 1 or limit > 100:
            limit = 50
        
        # Get files from service
        result = anthropic_file_service.list_files(limit=limit)
        
        if result['success']:
            return jsonify({
                'success': True,
                'files': result['files'],
                'total': result['total'],
                'limit': limit
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
            
    except Exception as e:
        logger.error(f"List files error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@file_upload_bp.route('/files/<file_id>', methods=['GET'])
@auth_service.require_auth
def get_file_metadata(file_id):
    """
    Get metadata for a specific file
    
    Args:
        file_id: Anthropic file ID
        
    Returns:
        JSON response with file metadata
    """
    try:
        current_user = get_current_user()
        
        # Get file metadata from service
        result = anthropic_file_service.get_file_metadata(file_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'file': result['file']
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 404
            
    except Exception as e:
        logger.error(f"Get file metadata error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@file_upload_bp.route('/files/<file_id>', methods=['DELETE'])
@auth_service.require_auth
def delete_file(file_id):
    """
    Delete a file from Anthropic Files API
    
    Args:
        file_id: Anthropic file ID to delete
        
    Returns:
        JSON response with deletion result
    """
    try:
        current_user = get_current_user()
        
        # Delete file using service
        result = anthropic_file_service.delete_file(file_id)
        
        if result['success']:
            # Log the deletion
            logging_service.audit(
                user_id=current_user.id,
                action_type=ActionType.DELETE,
                resource_type='file',
                resource_id=file_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                metadata={'deleted_by': current_user.id}
            )
            
            logger.info(f"File deleted by user {current_user.id}: {file_id}")
            
            return jsonify({
                'success': True,
                'message': 'File deleted successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
            
    except Exception as e:
        logger.error(f"Delete file error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@file_upload_bp.route('/files/validate', methods=['POST'])
@auth_service.require_auth
def validate_files():
    """
    Validate file IDs
    
    Expected JSON:
    {
        "file_ids": ["file_id_1", "file_id_2", ...]
    }
    
    Returns:
        JSON response with validation results
    """
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        if not data or 'file_ids' not in data:
            return jsonify({
                'success': False,
                'error': 'file_ids is required'
            }), 400
        
        file_ids = data['file_ids']
        
        # Validate file IDs
        result = anthropic_file_service.validate_file_ids(file_ids)
        
        if result['valid']:
            return jsonify({
                'success': True,
                'valid': True,
                'files': result['files']
            }), 200
        else:
            return jsonify({
                'success': True,
                'valid': False,
                'error': result['error'],
                'files': result.get('files', [])
            }), 200
            
    except Exception as e:
        logger.error(f"Validate files error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@file_upload_bp.route('/files/health', methods=['GET'])
@auth_service.require_auth
def health_check():
    """
    Health check for file service
    
    Returns:
        JSON response with service status
    """
    try:
        # Test service initialization
        is_ready = anthropic_file_service._ensure_initialized()
        
        return jsonify({
            'success': True,
            'service': 'anthropic_file_service',
            'status': 'healthy' if is_ready else 'unhealthy',
            'api_configured': bool(anthropic_file_service.api_key),
            'client_initialized': is_ready
        }), 200
        
    except Exception as e:
        logger.error(f"File service health check error: {str(e)}")
        return jsonify({
            'success': False,
            'service': 'anthropic_file_service',
            'status': 'unhealthy',
            'error': str(e)
        }), 500
