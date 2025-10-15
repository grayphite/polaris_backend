"""
PDFGeneratorService - Geração de Documentos PDF

Este service gerencia a geração de documentos PDF profissionais
para wealth planning, incluindo trusts, contratos e relatórios.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

# Imports para geração de PDF
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from weasyprint import HTML, CSS
except ImportError:
    # Fallback se bibliotecas não estiverem disponíveis
    SimpleDocTemplate = None
    Paragraph = None
    HTML = None

from src.extensions import db
from src.models import DocumentoGerado


@dataclass
class PDFGenerationResult:
    """Resultado da geração de PDF"""
    success: bool
    document_id: Optional[int] = None
    filename: str = ""
    file_path: str = ""
    file_size: int = 0
    error: Optional[str] = None
    generation_time: float = 0.0


@dataclass
class DocumentTemplate:
    """Template de documento"""
    name: str
    type: str
    description: str
    fields: List[str]
    html_template: str = ""
    css_styles: str = ""


class PDFGeneratorService:
    """Service para geração de documentos PDF"""

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), 'generated_documents')
        self.templates_dir = os.path.join(os.getcwd(), 'document_templates')

        # Criar diretórios se não existirem
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.templates_dir, exist_ok=True)

        # Templates disponíveis
        self.templates = {
            'trust_agreement': DocumentTemplate(
                name='Trust Agreement',
                type='trust',
                description='Comprehensive trust agreement for wealth planning',
                fields=['grantor_name', 'trustee_name', 'beneficiaries', 'trust_purpose', 'assets', 'jurisdiction'],
                html_template=self._get_trust_template(),
                css_styles=self._get_default_css()
            ),
            'estate_plan': DocumentTemplate(
                name='Estate Planning Report',
                type='estate',
                description='Detailed estate planning analysis and recommendations',
                fields=['client_name', 'assets_value', 'objectives', 'recommendations', 'timeline'],
                html_template=self._get_estate_template(),
                css_styles=self._get_default_css()
            ),
            'tax_analysis': DocumentTemplate(
                name='Tax Analysis Report',
                type='tax',
                description='International tax analysis and optimization strategies',
                fields=['client_name', 'current_structure', 'tax_implications', 'recommendations', 'savings'],
                html_template=self._get_tax_template(),
                css_styles=self._get_default_css()
            ),
            'compliance_report': DocumentTemplate(
                name='Compliance Report',
                type='compliance',
                description='Regulatory compliance analysis and requirements',
                fields=['entity_name', 'jurisdiction', 'requirements', 'status', 'actions_needed'],
                html_template=self._get_compliance_template(),
                css_styles=self._get_default_css()
            )
        }

    def generate_document(self,
                          template_type: str,
                          data: Dict[str, Any],
                          user_id: int,
                          custom_template: str = None) -> PDFGenerationResult:
        """
        Gerar documento PDF
        
        Args:
            template_type: Tipo de template (trust_agreement, estate_plan, etc.)
            data: Dados para preencher o template
            user_id: ID do usuário
            custom_template: Template customizado (opcional)
            
        Returns:
            PDFGenerationResult com resultado da geração
        """
        start_time = datetime.utcnow()

        try:
            # Validar template
            if template_type not in self.templates and not custom_template:
                return PDFGenerationResult(
                    success=False,
                    error=f"Template '{template_type}' não encontrado"
                )

            # Obter template
            if custom_template:
                template = DocumentTemplate(
                    name='Custom Template',
                    type='custom',
                    description='Custom document template',
                    fields=list(data.keys()),
                    html_template=custom_template,
                    css_styles=self._get_default_css()
                )
            else:
                template = self.templates[template_type]

            # Validar dados obrigatórios
            missing_fields = self._validate_template_data(template, data)
            if missing_fields:
                return PDFGenerationResult(
                    success=False,
                    error=f"Campos obrigatórios faltando: {', '.join(missing_fields)}"
                )

            # Gerar nome único para o arquivo
            filename = f"{template_type}_{uuid.uuid4().hex[:8]}.pdf"
            file_path = os.path.join(self.output_dir, filename)

            # Gerar PDF
            if HTML is not None:
                # Usar WeasyPrint (preferido)
                success = self._generate_with_weasyprint(template, data, file_path)
            elif SimpleDocTemplate is not None:
                # Fallback para ReportLab
                success = self._generate_with_reportlab(template, data, file_path)
            else:
                return PDFGenerationResult(
                    success=False,
                    error="Nenhuma biblioteca de geração de PDF disponível"
                )

            if not success:
                return PDFGenerationResult(
                    success=False,
                    error="Erro na geração do PDF"
                )

            # Verificar se arquivo foi criado
            if not os.path.exists(file_path):
                return PDFGenerationResult(
                    success=False,
                    error="Arquivo PDF não foi criado"
                )

            # Obter tamanho do arquivo
            file_size = os.path.getsize(file_path)

            # Salvar no banco de dados
            documento = DocumentoGerado(
                user_id=user_id,
                template_type=template_type,
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                template_data=data,
                generated=True
            )

            db.session.add(documento)
            db.session.commit()

            # Calcular tempo de geração
            generation_time = (datetime.utcnow() - start_time).total_seconds()

            return PDFGenerationResult(
                success=True,
                document_id=documento.id,
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                generation_time=generation_time
            )

        except Exception as e:
            db.session.rollback()
            # Limpar arquivo se houver erro
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)

            self._log_error(f"Erro na geração de PDF: {str(e)}", user_id)
            return PDFGenerationResult(
                success=False,
                error="Erro interno na geração do documento"
            )

    def get_document(self, document_id: int, user_id: int) -> Optional[DocumentoGerado]:
        """
        Obter documento gerado por ID
        
        Args:
            document_id: ID do documento
            user_id: ID do usuário (para verificação de permissão)
            
        Returns:
            DocumentoGerado ou None se não encontrado
        """
        try:
            return DocumentoGerado.query.filter_by(
                id=document_id,
                user_id=user_id
            ).first()

        except Exception as e:
            self._log_error(f"Erro ao obter documento: {str(e)}", user_id)
            return None

    def list_documents(self,
                       user_id: int,
                       template_type: str = None,
                       page: int = 1,
                       per_page: int = 20) -> Dict[str, Any]:
        """
        Listar documentos gerados do usuário
        
        Args:
            user_id: ID do usuário
            template_type: Filtrar por tipo de template (opcional)
            page: Página (padrão: 1)
            per_page: Itens por página (padrão: 20)
            
        Returns:
            Dict com documentos e paginação
        """
        try:
            query = DocumentoGerado.query.filter_by(user_id=user_id)

            if template_type:
                query = query.filter_by(template_type=template_type)

            paginated = query.order_by(DocumentoGerado.created_at.desc()).paginate(
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
        Excluir documento gerado
        
        Args:
            document_id: ID do documento
            user_id: ID do usuário
            
        Returns:
            True se excluído com sucesso
        """
        try:
            documento = DocumentoGerado.query.filter_by(
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

    def get_available_templates(self) -> List[Dict[str, Any]]:
        """
        Obter lista de templates disponíveis
        
        Returns:
            Lista de templates com metadados
        """
        try:
            templates_list = []

            for template_key, template in self.templates.items():
                templates_list.append({
                    'key': template_key,
                    'name': template.name,
                    'type': template.type,
                    'description': template.description,
                    'required_fields': template.fields
                })

            return templates_list

        except Exception as e:
            self._log_error(f"Erro ao obter templates: {str(e)}")
            return []

    def preview_template(self, template_type: str, sample_data: Dict = None) -> str:
        """
        Gerar preview HTML de um template
        
        Args:
            template_type: Tipo de template
            sample_data: Dados de exemplo (opcional)
            
        Returns:
            HTML do preview
        """
        try:
            if template_type not in self.templates:
                return "<p>Template não encontrado</p>"

            template = self.templates[template_type]

            # Usar dados de exemplo se não fornecidos
            if not sample_data:
                sample_data = self._get_sample_data(template_type)

            # Renderizar template
            html_content = self._render_template(template.html_template, sample_data)

            return f"""
            <html>
            <head>
                <style>{template.css_styles}</style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

        except Exception as e:
            self._log_error(f"Erro no preview: {str(e)}")
            return f"<p>Erro ao gerar preview: {str(e)}</p>"

    def get_generation_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Obter estatísticas de geração de documentos
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Dict com estatísticas
        """
        try:
            total_docs = DocumentoGerado.query.filter_by(user_id=user_id).count()

            # Estatísticas por tipo
            type_stats = db.session.query(
                DocumentoGerado.template_type,
                db.func.count(DocumentoGerado.id).label('count')
            ).filter_by(user_id=user_id).group_by(DocumentoGerado.template_type).all()

            # Tamanho total dos arquivos
            total_size = db.session.query(
                db.func.sum(DocumentoGerado.file_size)
            ).filter_by(user_id=user_id).scalar() or 0

            # Documentos gerados hoje
            today = datetime.utcnow().date()
            docs_today = DocumentoGerado.query.filter(
                DocumentoGerado.user_id == user_id,
                db.func.date(DocumentoGerado.created_at) == today
            ).count()

            return {
                'total_documents': total_docs,
                'documents_today': docs_today,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'by_template_type': {template_type: count for template_type, count in type_stats},
                'available_templates': len(self.templates)
            }

        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}", user_id)
            return {
                'total_documents': 0,
                'documents_today': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'by_template_type': {},
                'available_templates': 0
            }

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de geração de PDF
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Verificar diretórios
            output_dir_exists = os.path.exists(self.output_dir)
            output_dir_writable = os.access(self.output_dir, os.W_OK) if output_dir_exists else False

            # Verificar bibliotecas
            libraries_available = {
                'weasyprint': HTML is not None,
                'reportlab': SimpleDocTemplate is not None
            }

            # Teste de geração
            test_data = {'test_field': 'test_value'}
            test_template = "<html><body><h1>{{test_field}}</h1></body></html>"

            try:
                test_html = self._render_template(test_template, test_data)
                generation_test = bool(test_html and 'test_value' in test_html)
            except:
                generation_test = False

            # Espaço em disco
            disk_usage = self._get_disk_usage()

            status = "healthy"
            if not output_dir_writable:
                status = "unhealthy"
            elif not any(libraries_available.values()):
                status = "degraded"
            elif not generation_test:
                status = "warning"

            return {
                "status": status,
                "directories": {
                    "output_dir": {
                        "path": self.output_dir,
                        "exists": output_dir_exists,
                        "writable": output_dir_writable
                    }
                },
                "libraries": libraries_available,
                "templates": {
                    "available": len(self.templates),
                    "types": list(self.templates.keys())
                },
                "generation_test": generation_test,
                "disk_usage": disk_usage,
                "last_check": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }

    # Métodos privados auxiliares

    def _generate_with_weasyprint(self, template: DocumentTemplate, data: Dict, file_path: str) -> bool:
        """Gerar PDF usando WeasyPrint"""
        try:
            # Renderizar HTML
            html_content = self._render_template(template.html_template, data)

            # Criar HTML completo
            full_html = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <style>{template.css_styles}</style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

            # Gerar PDF
            HTML(string=full_html).write_pdf(file_path)

            return True

        except Exception as e:
            self._log_error(f"Erro no WeasyPrint: {str(e)}")
            return False

    def _generate_with_reportlab(self, template: DocumentTemplate, data: Dict, file_path: str) -> bool:
        """Gerar PDF usando ReportLab (fallback)"""
        try:
            # Criar documento
            doc = SimpleDocTemplate(file_path, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            # Título
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER
            )

            story.append(Paragraph(template.name, title_style))
            story.append(Spacer(1, 20))

            # Conteúdo baseado nos dados
            for key, value in data.items():
                if value:
                    # Título do campo
                    field_title = key.replace('_', ' ').title()
                    story.append(Paragraph(f"<b>{field_title}:</b>", styles['Heading2']))

                    # Valor do campo
                    story.append(Paragraph(str(value), styles['Normal']))
                    story.append(Spacer(1, 12))

            # Rodapé
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                alignment=TA_CENTER
            )

            story.append(Spacer(1, 30))
            story.append(Paragraph(
                f"Generated by POLARIS on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
                footer_style
            ))

            # Construir PDF
            doc.build(story)

            return True

        except Exception as e:
            self._log_error(f"Erro no ReportLab: {str(e)}")
            return False

    def _render_template(self, template: str, data: Dict) -> str:
        """Renderizar template com dados"""
        try:
            # Substituição simples de variáveis
            rendered = template

            for key, value in data.items():
                placeholder = f"{{{{{key}}}}}"
                rendered = rendered.replace(placeholder, str(value))

            return rendered

        except Exception as e:
            self._log_error(f"Erro na renderização: {str(e)}")
            return template

    def _validate_template_data(self, template: DocumentTemplate, data: Dict) -> List[str]:
        """Validar dados obrigatórios do template"""
        missing_fields = []

        for field in template.fields:
            if field not in data or not data[field]:
                missing_fields.append(field)

        return missing_fields

    def _get_sample_data(self, template_type: str) -> Dict[str, str]:
        """Obter dados de exemplo para template"""
        sample_data = {
            'trust_agreement': {
                'grantor_name': 'John Smith',
                'trustee_name': 'ABC Trust Company',
                'beneficiaries': 'Jane Smith, Robert Smith',
                'trust_purpose': 'Asset protection and estate planning',
                'assets': 'Real estate, securities, cash equivalents',
                'jurisdiction': 'Cayman Islands'
            },
            'estate_plan': {
                'client_name': 'Maria Silva',
                'assets_value': '$15,000,000',
                'objectives': 'Tax optimization, succession planning',
                'recommendations': 'Offshore trust structure, family holding company',
                'timeline': '6-12 months implementation'
            },
            'tax_analysis': {
                'client_name': 'Carlos Rodriguez',
                'current_structure': 'Individual ownership',
                'tax_implications': 'High tax burden, limited optimization',
                'recommendations': 'International holding structure',
                'savings': 'Estimated 25-30% tax savings annually'
            },
            'compliance_report': {
                'entity_name': 'Global Holdings Ltd.',
                'jurisdiction': 'British Virgin Islands',
                'requirements': 'Annual filings, beneficial ownership disclosure',
                'status': 'Compliant',
                'actions_needed': 'Update registered office address'
            }
        }

        return sample_data.get(template_type, {})

    def _get_trust_template(self) -> str:
        """Template HTML para Trust Agreement"""
        return """
        <div class="document">
            <h1>TRUST AGREEMENT</h1>
            
            <div class="section">
                <h2>PARTIES</h2>
                <p><strong>Grantor:</strong> {{grantor_name}}</p>
                <p><strong>Trustee:</strong> {{trustee_name}}</p>
                <p><strong>Beneficiaries:</strong> {{beneficiaries}}</p>
            </div>
            
            <div class="section">
                <h2>TRUST PURPOSE</h2>
                <p>{{trust_purpose}}</p>
            </div>
            
            <div class="section">
                <h2>TRUST ASSETS</h2>
                <p>{{assets}}</p>
            </div>
            
            <div class="section">
                <h2>GOVERNING LAW</h2>
                <p>This Trust Agreement shall be governed by the laws of {{jurisdiction}}.</p>
            </div>
            
            <div class="signature-section">
                <div class="signature-block">
                    <p>_________________________</p>
                    <p>Grantor: {{grantor_name}}</p>
                    <p>Date: _______________</p>
                </div>
                
                <div class="signature-block">
                    <p>_________________________</p>
                    <p>Trustee: {{trustee_name}}</p>
                    <p>Date: _______________</p>
                </div>
            </div>
        </div>
        """

    def _get_estate_template(self) -> str:
        """Template HTML para Estate Planning Report"""
        return """
        <div class="document">
            <h1>ESTATE PLANNING REPORT</h1>
            
            <div class="section">
                <h2>CLIENT INFORMATION</h2>
                <p><strong>Client:</strong> {{client_name}}</p>
                <p><strong>Total Assets:</strong> {{assets_value}}</p>
            </div>
            
            <div class="section">
                <h2>PLANNING OBJECTIVES</h2>
                <p>{{objectives}}</p>
            </div>
            
            <div class="section">
                <h2>RECOMMENDATIONS</h2>
                <p>{{recommendations}}</p>
            </div>
            
            <div class="section">
                <h2>IMPLEMENTATION TIMELINE</h2>
                <p>{{timeline}}</p>
            </div>
            
            <div class="footer">
                <p><em>This report is confidential and prepared for the exclusive use of {{client_name}}.</em></p>
            </div>
        </div>
        """

    def _get_tax_template(self) -> str:
        """Template HTML para Tax Analysis Report"""
        return """
        <div class="document">
            <h1>TAX ANALYSIS REPORT</h1>
            
            <div class="section">
                <h2>CLIENT</h2>
                <p>{{client_name}}</p>
            </div>
            
            <div class="section">
                <h2>CURRENT STRUCTURE</h2>
                <p>{{current_structure}}</p>
            </div>
            
            <div class="section">
                <h2>TAX IMPLICATIONS</h2>
                <p>{{tax_implications}}</p>
            </div>
            
            <div class="section">
                <h2>RECOMMENDATIONS</h2>
                <p>{{recommendations}}</p>
            </div>
            
            <div class="section">
                <h2>PROJECTED SAVINGS</h2>
                <p>{{savings}}</p>
            </div>
        </div>
        """

    def _get_compliance_template(self) -> str:
        """Template HTML para Compliance Report"""
        return """
        <div class="document">
            <h1>COMPLIANCE REPORT</h1>
            
            <div class="section">
                <h2>ENTITY INFORMATION</h2>
                <p><strong>Entity:</strong> {{entity_name}}</p>
                <p><strong>Jurisdiction:</strong> {{jurisdiction}}</p>
            </div>
            
            <div class="section">
                <h2>COMPLIANCE REQUIREMENTS</h2>
                <p>{{requirements}}</p>
            </div>
            
            <div class="section">
                <h2>CURRENT STATUS</h2>
                <p>{{status}}</p>
            </div>
            
            <div class="section">
                <h2>ACTIONS NEEDED</h2>
                <p>{{actions_needed}}</p>
            </div>
        </div>
        """

    def _get_default_css(self) -> str:
        """CSS padrão para documentos"""
        return """
        body {
            font-family: 'Times New Roman', serif;
            font-size: 12pt;
            line-height: 1.6;
            margin: 1in;
            color: #333;
        }
        
        .document {
            max-width: 8.5in;
            margin: 0 auto;
        }
        
        h1 {
            text-align: center;
            font-size: 18pt;
            font-weight: bold;
            margin-bottom: 30pt;
            text-transform: uppercase;
        }
        
        h2 {
            font-size: 14pt;
            font-weight: bold;
            margin-top: 20pt;
            margin-bottom: 10pt;
            border-bottom: 1px solid #ccc;
            padding-bottom: 5pt;
        }
        
        .section {
            margin-bottom: 20pt;
        }
        
        .signature-section {
            margin-top: 50pt;
            display: flex;
            justify-content: space-between;
        }
        
        .signature-block {
            width: 45%;
            text-align: center;
        }
        
        .footer {
            margin-top: 50pt;
            font-size: 10pt;
            text-align: center;
            font-style: italic;
        }
        
        p {
            margin-bottom: 10pt;
            text-align: justify;
        }
        
        strong {
            font-weight: bold;
        }
        
        @page {
            margin: 1in;
            @bottom-center {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 10pt;
            }
        }
        """

    def _get_disk_usage(self) -> Dict[str, Any]:
        """Obter uso do disco"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.output_dir)

            return {
                'total_gb': round(total / (1024 ** 3), 2),
                'used_gb': round(used / (1024 ** 3), 2),
                'free_gb': round(free / (1024 ** 3), 2),
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
            log_data = {
                'error': error_msg,
                'user_id': user_id,
                'service': 'PDFGeneratorService',
                'timestamp': datetime.utcnow().isoformat()
            }
            print(f"[ERROR] PDFGeneratorService: {error_msg}")
        except:
            print(f"[ERROR] PDFGeneratorService: {error_msg}")


# Instância global do service
pdf_generator_service = PDFGeneratorService()
