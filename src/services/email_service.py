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
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.logger = logging.getLogger(self.__class__.__name__)

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
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)

                # Enviar email
                to_list = (to_emails if isinstance(to_emails, list)
                           else [to_emails])
                server.send_message(msg, to_addrs=to_list)

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


# Instância global do service
email_service = EmailService()
