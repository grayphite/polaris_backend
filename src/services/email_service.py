"""
EmailService - Sistema de Notificações por Email

Este service gerencia envio de emails, templates e notificações
do sistema POLARIS.
"""

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Optional, Union
from string import Template
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Estrutura de uma mensagem de email"""
    to: Union[str, List[str]]
    subject: str
    text_content: Optional[str] = None
    html_content: Optional[str] = None
    attachments: Optional[List[Dict]] = None
    priority: str = 'normal'  # high, normal, low


class EmailService:
    """Service para envio de emails e notificações"""

    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_use_tls = os.getenv('SMTP_USE_TLS', 'True').lower() == 'true'
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Log configuration status
        if self.smtp_user and self.smtp_password:
            self.logger.info(f"Email service configured: {self.smtp_host}:{self.smtp_port}")
        else:
            self.logger.warning("Email service not fully configured - SMTP credentials missing")

    # ---------------------- Template Utilities ----------------------
    def _templates_dir(self) -> str:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates/email'))
        return base_dir

    def _load_template(self, filename: str) -> str:
        path = os.path.join(self._templates_dir(), filename)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _render_template(self, filename: str, variables: Dict[str, Union[str, int]]) -> str:
        raw = self._load_template(filename)
        return Template(raw).safe_substitute(variables)

    def _build_personal_message_block(self, message: Optional[str]) -> str:
        if not message:
            return ''
        return (
            '<table width="100%" cellpadding="0" cellspacing="0" '
            'style="margin-top:20px;background:#fff5f5;border-left:4px solid #f56565;'
            'padding:0;border-radius:0 8px 8px 0;">'
            '<tr><td style="padding:16px 20px;">'
            '<div style="color:#c53030;font-weight:600;margin-bottom:8px;">Mensagem Pessoal</div>'
            f'<div style="color:#4a5568;font-size:14px;line-height:1.6;font-style:italic;">"{message}"</div>'
            '</td></tr></table>'
        )

    # ---------------------- Core send function ----------------------
    def send_email(self, message: EmailMessage) -> Dict:
        """
        Envia um email
        
        Args:
            message: Dados da mensagem
        
        Returns:
            Dict com resultado do envio
        """
        try:
            if not self.smtp_user or not self.smtp_password:
                self.logger.warning("SMTP não configurado - simulando envio")
                return {
                    'success': True,
                    'message': 'Email simulado (SMTP não configurado)',
                    'sent_to': (message.to if isinstance(message.to, list)
                                else [message.to])
                }

            # Preparar mensagem
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = (', '.join(message.to) if isinstance(message.to, list)
                         else message.to)
            msg['Subject'] = message.subject

            # Adicionar conteúdo
            if message.text_content:
                text_part = MIMEText(message.text_content, 'plain', 'utf-8')
                msg.attach(text_part)

            if message.html_content:
                html_part = MIMEText(message.html_content, 'html', 'utf-8')
                msg.attach(html_part)

            # Adicionar anexos se houver
            if message.attachments:
                for attachment in message.attachments:
                    self._add_attachment(msg, attachment)

            # Enviar via SMTP
            return self._send_via_smtp(msg, message.to)

        except Exception as e:
            error_msg = f"Erro ao enviar email: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict):
        """Adiciona anexo à mensagem"""
        try:
            if 'path' in attachment and os.path.exists(attachment['path']):
                with open(attachment['path'], 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())

                encoders.encode_base64(part)
                filename = attachment.get('filename',
                                          os.path.basename(attachment['path']))
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {filename}'
                )
                msg.attach(part)
        except Exception as e:
            self.logger.error(f"Erro ao adicionar anexo: {str(e)}")

    def _send_via_smtp(self, msg: MIMEMultipart, to_emails) -> Dict:
        """Envia mensagem via SMTP"""
        try:
            # Conectar ao servidor SMTP
            context = ssl.create_default_context()
            
            # For development/testing, disable certificate verification if needed
            # This is common on macOS where certificate verification can fail
            try:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    if self.smtp_use_tls:
                        server.starttls(context=context)
                    server.login(self.smtp_user, self.smtp_password)
                    
                    # Enviar email
                    to_list = (to_emails if isinstance(to_emails, list)
                               else [to_emails])
                    server.send_message(msg, to_addrs=to_list)
                    
            except ssl.SSLError as ssl_error:
                if "certificate verify failed" in str(ssl_error):
                    self.logger.warning("SSL certificate verification failed, retrying with unverified context")
                    # Retry with unverified SSL context
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                        if self.smtp_use_tls:
                            server.starttls(context=context)
                        server.login(self.smtp_user, self.smtp_password)
                        
                        # Enviar email
                        to_list = (to_emails if isinstance(to_emails, list)
                                   else [to_emails])
                        server.send_message(msg, to_addrs=to_list)
                else:
                    raise ssl_error

            # Get the recipient list for logging
            to_list = (to_emails if isinstance(to_emails, list) else [to_emails])
            
            self.logger.info(f"Email enviado para: {to_list}")
            return {
                'success': True,
                'message': 'Email enviado com sucesso',
                'sent_to': to_list
            }

        except Exception as e:
            error_msg = f"Erro no envio SMTP: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def send_welcome_email(self, user_email: str, user_name: str) -> Dict:
        """Envia email de boas-vindas para novo usuário"""
        subject = "Bem-vindo ao POLARIS!"

        text_content = f"""
Olá {user_name},

Bem-vindo ao POLARIS - sua plataforma de wealth planning com IA!

Estamos animados para tê-lo conosco. Agora você pode:
- Gerenciar seus clientes de forma eficiente
- Gerar documentos profissionais com IA
- Acessar análises financeiras avançadas

Comece explorando sua nova conta.

Atenciosamente,
Equipe POLARIS
"""

        html_content = f"""
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
    <h2 style="color: #2c5282;">Bem-vindo ao POLARIS!</h2>
    
    <p>Olá <strong>{user_name}</strong>,</p>
    
    <p>Bem-vindo ao POLARIS - sua plataforma de wealth planning com IA!</p>
    
    <p>Estamos animados para tê-lo conosco. Agora você pode:</p>
    <ul>
        <li>Gerenciar seus clientes de forma eficiente</li>
        <li>Gerar documentos profissionais com IA</li>
        <li>Acessar análises financeiras avançadas</li>
    </ul>
    
    <p>Comece explorando sua nova conta.</p>
    
    <p>Atenciosamente,<br>
    <strong>Equipe POLARIS</strong></p>
</body>
</html>
"""

        message = EmailMessage(
            to=user_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )

        return self.send_email(message)

    def send_reset_password_email(
            self, user_email: str, reset_link: str
    ) -> Dict:
        """Envia email para redefinição de senha"""

        subject = "Redefinição de Senha POLARIS"
        text_content = f"""
Olá,
Recebemos uma solicitação para redefinir sua senha do POLARIS.
Para redefinir sua senha, clique no link abaixo:
{reset_link}
Se você não solicitou essa alteração, ignore este email.
Atenciosamente,
Equipe POLARIS
"""

        html_content = f"""
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
    <h2 style="color: #2c5282;">Redefinição de Senha POLARIS</h2>
    <p>Olá,</p>
    <p>Recebemos uma solicitação para redefinir sua senha do POLARIS.</p>
    <p>Para redefinir sua senha, clique no link abaixo:</p>
    <p><a href="{reset_link}" style="color: #3182ce;">Redefinir Senha</a></p>
    <p>Se você não solicitou essa alteração, ignore este email.</p>
    <p>Atenciosamente,<br>
    <strong>Equipe POLARIS</strong></p>
</body>
</html>
"""

        message = EmailMessage(
            to=user_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )

        return self.send_email(message)

    def send_document_notification(self, user_email: str,
                                   document_name: str) -> Dict:
        """Envia notificação de documento gerado"""
        subject = f"Documento '{document_name}' foi gerado"

        text_content = f"""
Olá,

O documento '{document_name}' foi gerado com sucesso no POLARIS.

Você pode acessá-lo em sua conta.

Atenciosamente,
Sistema POLARIS
"""

        message = EmailMessage(
            to=user_email,
            subject=subject,
            text_content=text_content
        )

        return self.send_email(message)

    def send_team_invitation_email(self, invited_email: str, team_name: str, 
                                   inviter_name: str, invitation_link: str,
                                   role: str = 'member', message: str = None,
                                   expires_in_days: int = 7) -> Dict:
        """Envia email de convite para equipe"""
        
        subject = f"Você foi convidado para a equipe '{team_name}' no POLARIS"
        
        # Plain text fallback
        text_content = (
            f"Olá!\n\n"
            f"Você foi convidado por {inviter_name} para participar da equipe '{team_name}' no POLARIS.\n\n"
            f"Detalhes do convite:\n- Equipe: {team_name}\n- Função: {role}\n- Convite válido por: {expires_in_days} dias\n- Convidado por: {inviter_name}\n\n"
            f"{('Mensagem pessoal: ' + message) if message else ''}"
            f"Para aceitar o convite e criar sua conta, clique no link abaixo:\n{invitation_link}\n\n"
            f"Se você não deseja participar desta equipe, pode simplesmente ignorar este email.\n\n"
            f"Atenciosamente,\nEquipe POLARIS"
        )

        # HTML via template
        html_content = self._render_template(
            'invitation_email.html',
            {
                'team_name': team_name,
                'inviter_name': inviter_name,
                'role': role,
                'expires_in_days': expires_in_days,
                'invitation_link': invitation_link,
                'current_year': datetime.now().year,
                'personal_message_block': self._build_personal_message_block(message)
            }
        )

        email_message = EmailMessage(
            to=invited_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )

        return self.send_email(email_message)

    def send_invitation_accepted_notification(self, inviter_email: str, 
                                           invited_user_name: str, 
                                           team_name: str) -> Dict:
        """Envia notificação quando convite é aceito"""
        
        subject = f"{invited_user_name} aceitou seu convite para '{team_name}'"
        
        # Text fallback
        text_content = (
            "Olá!\n\n"
            f"{invited_user_name} aceitou seu convite para participar da equipe '{team_name}' no POLARIS.\n\n"
            f"Agora você pode colaborar com {invited_user_name} em projetos e tarefas da equipe.\n\n"
            "Acesse sua conta para ver os detalhes da equipe.\n\n"
            "Atenciosamente,\nEquipe POLARIS"
        )

        html_content = self._render_template(
            'invitation_accepted.html',
            {
                'invited_user_name': invited_user_name,
                'team_name': team_name,
                'current_year': datetime.now().year
            }
        )

        message = EmailMessage(
            to=inviter_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )

        return self.send_email(message)

    def send_invitation_declined_notification(self, inviter_email: str, 
                                            invited_user_name: str, 
                                            team_name: str) -> Dict:
        """Envia notificação quando convite é recusado"""
        
        subject = f"{invited_user_name} recusou seu convite para '{team_name}'"
        
        text_content = (
            "Olá!\n\n"
            f"{invited_user_name} recusou seu convite para participar da equipe '{team_name}' no POLARIS.\n\n"
            "Você pode tentar convidar outros membros para sua equipe.\n\n"
            "Atenciosamente,\nEquipe POLARIS"
        )

        html_content = self._render_template(
            'invitation_declined.html',
            {
                'invited_user_name': invited_user_name,
                'team_name': team_name,
                'current_year': datetime.now().year
            }
        )

        message = EmailMessage(
            to=inviter_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )

        return self.send_email(message)


# Instância global do service
email_service = EmailService()
