"""
DocumentProcessorService - Processamento de Documentos

Este service gerencia upload, processamento e extração de conteúdo
de documentos PDF, DOC, DOCX, TXT para o sistema MCP.
"""

import os
import uuid
import mimetypes
from datetime import datetime
from typing import Dict, List, Optional, Any, BinaryIO
from dataclasses import dataclass
from pathlib import Path
import hashlib

# Imports para processamento de documentos
try:
    import PyPDF2
    import pdfplumber
    from docx import Document as DocxDocument
    import textract
except ImportError:
    # Fallback se bibliotecas não estiverem disponíveis
    PyPDF2 = None
    pdfplumber = None
    DocxDocument = None
    textract = None

from src.database import db
from src.models import DocumentoUpload


@dataclass
class ProcessingResult:
    """Resultado do processamento de documento"""
    success: bool
    document_id: Optional[int] = None
    filename: str = ""
    content: str = ""
    metadata: Dict = None
    error: Optional[str] = None
    chunks: List[str] = None
    word_count: int = 0
    processing_time: float = 0.0


@dataclass
class DocumentChunk:
    """Chunk de documento para indexação"""
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: Dict = None


class DocumentProcessorService:
    """Service para processamento de documentos"""
    
    def __init__(self):
        self.upload_dir = os.path.join(os.getcwd(), 'uploads')
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.rtf'}
        self.chunk_size = 1000  # Caracteres por chunk
        self.chunk_overlap = 200  # Sobreposição entre chunks
        
        # Criar diretório de upload se não existir
        os.makedirs(self.upload_dir, exist_ok=True)
    
    def upload_document(self, 
                       file: BinaryIO,
                       filename: str,
                       user_id: int,
                       category: str = None,
                       metadata: Dict = None) -> ProcessingResult:
        """
        Upload e processamento de documento
        
        Args:
            file: Arquivo binário
            filename: Nome do arquivo
            user_id: ID do usuário
            category: Categoria do documento (opcional)
            metadata: Metadados adicionais (opcional)
            
        Returns:
            ProcessingResult com resultado do processamento
        """
        start_time = datetime.utcnow()
        
        try:
            # Validar arquivo
            validation_error = self._validate_file(file, filename)
            if validation_error:
                return ProcessingResult(
                    success=False,
                    error=validation_error
                )
            
            # Gerar nome único para o arquivo
            file_extension = Path(filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(self.upload_dir, unique_filename)
            
            # Salvar arquivo
            file.seek(0)  # Reset file pointer
            file_content = file.read()
            
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            # Calcular hash do arquivo
            file_hash = hashlib.md5(file_content).hexdigest()
            
            # Verificar se arquivo já existe (por hash)
            existing_doc = DocumentoUpload.query.filter_by(
                file_hash=file_hash,
                user_id=user_id
            ).first()
            
            if existing_doc:
                # Remover arquivo duplicado
                os.remove(file_path)
                return ProcessingResult(
                    success=False,
                    error="Documento já foi enviado anteriormente"
                )
            
            # Extrair conteúdo
            content = self._extract_content(file_path, file_extension)
            if not content:
                os.remove(file_path)
                return ProcessingResult(
                    success=False,
                    error="Não foi possível extrair conteúdo do documento"
                )
            
            # Criar chunks
            chunks = self._create_chunks(content)
            
            # Detectar MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Preparar metadados
            doc_metadata = {
                'original_filename': filename,
                'file_extension': file_extension,
                'file_size': len(file_content),
                'mime_type': mime_type,
                'word_count': len(content.split()),
                'chunk_count': len(chunks),
                'category': category,
                'processing_date': datetime.utcnow().isoformat()
            }
            
            if metadata:
                doc_metadata.update(metadata)
            
            # Salvar no banco de dados
            documento = DocumentoUpload(
                user_id=user_id,
                filename=unique_filename,
                original_filename=filename,
                file_path=file_path,
                file_size=len(file_content),
                file_hash=file_hash,
                mime_type=mime_type,
                content_extracted=content,
                metadata=doc_metadata,
                processed=True,
                category=category or 'general'
            )
            
            db.session.add(documento)
            db.session.commit()
            
            # Calcular tempo de processamento
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ProcessingResult(
                success=True,
                document_id=documento.id,
                filename=filename,
                content=content,
                metadata=doc_metadata,
                chunks=[chunk.content for chunk in chunks],
                word_count=len(content.split()),
                processing_time=processing_time
            )
            
        except Exception as e:
            db.session.rollback()
            # Limpar arquivo se houver erro
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            
            self._log_error(f"Erro no upload: {str(e)}", user_id)
            return ProcessingResult(
                success=False,
                error="Erro interno no processamento do documento"
            )
    
    def get_document(self, document_id: int, user_id: int) -> Optional[DocumentoUpload]:
        """
        Obter documento por ID
        
        Args:
            document_id: ID do documento
            user_id: ID do usuário (para verificação de permissão)
            
        Returns:
            DocumentoUpload ou None se não encontrado
        """
        try:
            return DocumentoUpload.query.filter_by(
                id=document_id,
                user_id=user_id
            ).first()
            
        except Exception as e:
            self._log_error(f"Erro ao obter documento: {str(e)}", user_id)
            return None
    
    def list_documents(self, 
                      user_id: int,
                      category: str = None,
                      page: int = 1,
                      per_page: int = 20) -> Dict[str, Any]:
        """
        Listar documentos do usuário
        
        Args:
            user_id: ID do usuário
            category: Filtrar por categoria (opcional)
            page: Página (padrão: 1)
            per_page: Itens por página (padrão: 20)
            
        Returns:
            Dict com documentos e paginação
        """
        try:
            query = DocumentoUpload.query.filter_by(user_id=user_id)
            
            if category:
                query = query.filter_by(category=category)
            
            paginated = query.order_by(DocumentoUpload.created_at.desc()).paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            return {
                'documents': [doc.to_dict() for doc in paginated.items],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': paginated.total,
                    'pages': paginated.pages,
                    'has_next': paginated.has_next,
                    'has_prev': paginated.has_prev
                }
            }
            
        except Exception as e:
            self._log_error(f"Erro ao listar documentos: {str(e)}", user_id)
            return {
                'documents': [],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': 0,
                    'pages': 0,
                    'has_next': False,
                    'has_prev': False
                }
            }
    
    def delete_document(self, document_id: int, user_id: int) -> bool:
        """
        Excluir documento
        
        Args:
            document_id: ID do documento
            user_id: ID do usuário
            
        Returns:
            True se excluído com sucesso
        """
        try:
            documento = DocumentoUpload.query.filter_by(
                id=document_id,
                user_id=user_id
            ).first()
            
            if not documento:
                return False
            
            # Remover arquivo físico
            if os.path.exists(documento.file_path):
                os.remove(documento.file_path)
            
            # Remover do banco
            db.session.delete(documento)
            db.session.commit()
            
            return True
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro ao excluir documento: {str(e)}", user_id)
            return False
    
    def reprocess_document(self, document_id: int, user_id: int) -> ProcessingResult:
        """
        Reprocessar documento existente
        
        Args:
            document_id: ID do documento
            user_id: ID do usuário
            
        Returns:
            ProcessingResult com resultado do reprocessamento
        """
        try:
            documento = self.get_document(document_id, user_id)
            if not documento:
                return ProcessingResult(
                    success=False,
                    error="Documento não encontrado"
                )
            
            # Reextrair conteúdo
            file_extension = Path(documento.original_filename).suffix.lower()
            content = self._extract_content(documento.file_path, file_extension)
            
            if not content:
                return ProcessingResult(
                    success=False,
                    error="Não foi possível reextrair conteúdo"
                )
            
            # Recriar chunks
            chunks = self._create_chunks(content)
            
            # Atualizar documento
            documento.content_extracted = content
            documento.processed = True
            documento.updated_at = datetime.utcnow()
            
            # Atualizar metadados
            if documento.metadata:
                documento.metadata.update({
                    'word_count': len(content.split()),
                    'chunk_count': len(chunks),
                    'reprocessed_at': datetime.utcnow().isoformat()
                })
            
            db.session.commit()
            
            return ProcessingResult(
                success=True,
                document_id=documento.id,
                filename=documento.original_filename,
                content=content,
                metadata=documento.metadata,
                chunks=[chunk.content for chunk in chunks],
                word_count=len(content.split())
            )
            
        except Exception as e:
            db.session.rollback()
            self._log_error(f"Erro no reprocessamento: {str(e)}", user_id)
            return ProcessingResult(
                success=False,
                error="Erro interno no reprocessamento"
            )
    
    def get_document_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Obter estatísticas dos documentos do usuário
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Dict com estatísticas
        """
        try:
            total_docs = DocumentoUpload.query.filter_by(user_id=user_id).count()
            
            # Estatísticas por categoria
            category_stats = db.session.query(
                DocumentoUpload.category,
                db.func.count(DocumentoUpload.id).label('count')
            ).filter_by(user_id=user_id).group_by(DocumentoUpload.category).all()
            
            # Tamanho total dos arquivos
            total_size = db.session.query(
                db.func.sum(DocumentoUpload.file_size)
            ).filter_by(user_id=user_id).scalar() or 0
            
            # Documentos processados
            processed_docs = DocumentoUpload.query.filter_by(
                user_id=user_id,
                processed=True
            ).count()
            
            return {
                'total_documents': total_docs,
                'processed_documents': processed_docs,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'categories': {cat: count for cat, count in category_stats},
                'processing_rate': round((processed_docs / total_docs * 100), 2) if total_docs > 0 else 0
            }
            
        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}", user_id)
            return {
                'total_documents': 0,
                'processed_documents': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'categories': {},
                'processing_rate': 0
            }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de processamento
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Verificar diretório de upload
            upload_dir_exists = os.path.exists(self.upload_dir)
            upload_dir_writable = os.access(self.upload_dir, os.W_OK) if upload_dir_exists else False
            
            # Verificar bibliotecas de processamento
            libraries_available = {
                'PyPDF2': PyPDF2 is not None,
                'pdfplumber': pdfplumber is not None,
                'python-docx': DocxDocument is not None,
                'textract': textract is not None
            }
            
            # Espaço em disco disponível
            disk_usage = self._get_disk_usage()
            
            return {
                "status": "healthy" if upload_dir_exists and upload_dir_writable else "unhealthy",
                "upload_directory": {
                    "path": self.upload_dir,
                    "exists": upload_dir_exists,
                    "writable": upload_dir_writable
                },
                "libraries": libraries_available,
                "disk_usage": disk_usage,
                "config": {
                    "max_file_size_mb": self.max_file_size / (1024 * 1024),
                    "allowed_extensions": list(self.allowed_extensions),
                    "chunk_size": self.chunk_size,
                    "chunk_overlap": self.chunk_overlap
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
    
    def _validate_file(self, file: BinaryIO, filename: str) -> Optional[str]:
        """Validar arquivo enviado"""
        # Verificar extensão
        file_extension = Path(filename).suffix.lower()
        if file_extension not in self.allowed_extensions:
            return f"Tipo de arquivo não suportado. Permitidos: {', '.join(self.allowed_extensions)}"
        
        # Verificar tamanho
        file.seek(0, 2)  # Ir para o final do arquivo
        file_size = file.tell()
        file.seek(0)  # Voltar ao início
        
        if file_size > self.max_file_size:
            return f"Arquivo muito grande. Máximo: {self.max_file_size / (1024 * 1024):.1f}MB"
        
        if file_size == 0:
            return "Arquivo está vazio"
        
        return None
    
    def _extract_content(self, file_path: str, file_extension: str) -> str:
        """Extrair conteúdo do arquivo"""
        try:
            if file_extension == '.txt':
                return self._extract_txt(file_path)
            elif file_extension == '.pdf':
                return self._extract_pdf(file_path)
            elif file_extension in ['.doc', '.docx']:
                return self._extract_doc(file_path)
            elif file_extension == '.rtf':
                return self._extract_rtf(file_path)
            else:
                return ""
                
        except Exception as e:
            self._log_error(f"Erro na extração de conteúdo: {str(e)}")
            return ""
    
    def _extract_txt(self, file_path: str) -> str:
        """Extrair conteúdo de arquivo TXT"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Tentar outras codificações
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            return ""
    
    def _extract_pdf(self, file_path: str) -> str:
        """Extrair conteúdo de arquivo PDF"""
        content = ""
        
        # Tentar com pdfplumber primeiro (melhor para tabelas)
        if pdfplumber:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            content += page_text + "\n"
                if content.strip():
                    return content
            except:
                pass
        
        # Fallback para PyPDF2
        if PyPDF2:
            try:
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            content += page_text + "\n"
                if content.strip():
                    return content
            except:
                pass
        
        # Fallback para textract
        if textract:
            try:
                content = textract.process(file_path).decode('utf-8')
                return content
            except:
                pass
        
        return content
    
    def _extract_doc(self, file_path: str) -> str:
        """Extrair conteúdo de arquivo DOC/DOCX"""
        # Tentar com python-docx para DOCX
        if DocxDocument and file_path.endswith('.docx'):
            try:
                doc = DocxDocument(file_path)
                content = []
                for paragraph in doc.paragraphs:
                    content.append(paragraph.text)
                return '\n'.join(content)
            except:
                pass
        
        # Fallback para textract
        if textract:
            try:
                content = textract.process(file_path).decode('utf-8')
                return content
            except:
                pass
        
        return ""
    
    def _extract_rtf(self, file_path: str) -> str:
        """Extrair conteúdo de arquivo RTF"""
        if textract:
            try:
                content = textract.process(file_path).decode('utf-8')
                return content
            except:
                pass
        
        return ""
    
    def _create_chunks(self, content: str) -> List[DocumentChunk]:
        """Criar chunks do conteúdo para indexação"""
        chunks = []
        
        if not content:
            return chunks
        
        # Dividir em chunks com sobreposição
        start = 0
        chunk_index = 0
        
        while start < len(content):
            end = start + self.chunk_size
            
            # Se não é o último chunk, tentar quebrar em uma palavra
            if end < len(content):
                # Procurar por espaço ou quebra de linha próxima
                for i in range(end, max(start + self.chunk_size // 2, end - 100), -1):
                    if content[i] in [' ', '\n', '\t', '.', '!', '?']:
                        end = i + 1
                        break
            
            chunk_content = content[start:end].strip()
            
            if chunk_content:
                chunk = DocumentChunk(
                    content=chunk_content,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end,
                    metadata={
                        'length': len(chunk_content),
                        'word_count': len(chunk_content.split())
                    }
                )
                chunks.append(chunk)
                chunk_index += 1
            
            # Próximo chunk com sobreposição
            start = end - self.chunk_overlap
            
            # Evitar loop infinito
            if start >= end:
                break
        
        return chunks
    
    def _get_disk_usage(self) -> Dict[str, Any]:
        """Obter uso do disco"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.upload_dir)
            
            return {
                'total_gb': round(total / (1024**3), 2),
                'used_gb': round(used / (1024**3), 2),
                'free_gb': round(free / (1024**3), 2),
                'usage_percent': round((used / total) * 100, 2)
            }
        except:
            return {
                'total_gb': 0,
                'used_gb': 0,
                'free_gb': 0,
                'usage_percent': 0
            }
    
    def _log_error(self, error_msg: str, user_id: int = None):
        """Log de erro"""
        try:
            # Aqui integraria com LoggingService quando implementado
            log_data = {
                'error': error_msg,
                'user_id': user_id,
                'service': 'DocumentProcessorService',
                'timestamp': datetime.utcnow().isoformat()
            }
            print(f"[ERROR] DocumentProcessorService: {error_msg}")
        except:
            print(f"[ERROR] DocumentProcessorService: {error_msg}")

# Instância global do service
document_processor_service = DocumentProcessorService()

