"""
Modelos para auditoria e logging
"""
from datetime import datetime

from src.extensions import db


class AuditLog(db.Model):
    """Modelo para logs de auditoria"""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # New fields for enhanced audit logging
    action_type = db.Column(db.String(50))
    resource_type = db.Column(db.String(100))
    resource_id = db.Column(db.String(100))
    
    # Audit details
    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    
    # Legacy fields (kept for backward compatibility)
    action = db.Column(db.String(255))
    resource = db.Column(db.String(255))
    details = db.Column(db.Text)
    
    # Request metadata
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    session_id = db.Column(db.String(255))
    
    # Status fields
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    audit_metadata = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action_type': self.action_type,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'old_values': self.old_values,
            'new_values': self.new_values,
            'action': self.action,
            'resource': self.resource,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'session_id': self.session_id,
            'success': self.success,
            'error_message': self.error_message,
            'metadata': self.audit_metadata,
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None)
        }
