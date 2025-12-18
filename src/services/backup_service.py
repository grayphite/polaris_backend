"""
BackupService - Sistema de Backup e Recuperação

Este service gerencia backup automático de dados, arquivos
e configurações do sistema POLARIS.
"""

import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

from src.services.logging_service import logging_service


class BackupType(Enum):
    """Tipos de backup"""
    FULL = "full"
    INCREMENTAL = "incremental"
    DATABASE = "database"
    FILES = "files"
    CONFIG = "config"


class BackupStatus(Enum):
    """Status do backup"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackupJob:
    """Job de backup"""
    id: str
    backup_type: BackupType
    status: BackupStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size_mb: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BackupConfig:
    """Configuração de backup"""
    enabled: bool
    backup_dir: str
    retention_days: int
    max_backups: int
    schedule_hour: int
    include_database: bool
    include_files: bool
    include_config: bool
    compression_enabled: bool
    encryption_enabled: bool


class BackupService:
    """Service para backup e recuperação"""

    def __init__(self):
        # Configurações
        self.backup_dir = os.path.join(os.getcwd(), 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)

        self.config = BackupConfig(
            enabled=os.getenv('BACKUP_ENABLED', 'true').lower() == 'true',
            backup_dir=self.backup_dir,
            retention_days=int(os.getenv('BACKUP_RETENTION_DAYS', '30')),
            max_backups=int(os.getenv('BACKUP_MAX_BACKUPS', '10')),
            schedule_hour=int(os.getenv('BACKUP_SCHEDULE_HOUR', '2')),
            include_database=True,
            include_files=True,
            include_config=True,
            compression_enabled=True,
            encryption_enabled=False
        )

        # Jobs ativos
        self.active_jobs = {}
        self.job_history = []

        # Configurações de banco
        self.database_url = os.getenv('DATABASE_URL', '')

        # Diretórios para backup
        self.backup_paths = {
            'uploads': os.path.join(os.getcwd(), 'uploads'),
            'logs': os.path.join(os.getcwd(), 'logs'),
            'config': os.path.join(os.getcwd(), 'config'),
            'static': os.path.join(os.getcwd(), 'src', 'static')
        }

    def create_backup(self,
                      backup_type: BackupType = BackupType.FULL,
                      include_database: bool = True,
                      include_files: bool = True,
                      include_config: bool = True) -> str:
        """
        Criar backup
        
        Args:
            backup_type: Tipo de backup
            include_database: Incluir banco de dados
            include_files: Incluir arquivos
            include_config: Incluir configurações
            
        Returns:
            ID do job de backup
        """
        try:
            if not self.config.enabled:
                raise Exception("Backup está desabilitado")

            # Criar job
            job_id = f"backup_{int(time.time())}"
            job = BackupJob(
                id=job_id,
                backup_type=backup_type,
                status=BackupStatus.PENDING,
                created_at=datetime.utcnow(),
                metadata={
                    'include_database': include_database,
                    'include_files': include_files,
                    'include_config': include_config
                }
            )

            self.active_jobs[job_id] = job

            # Executar backup em thread separada
            thread = threading.Thread(
                target=self._execute_backup,
                args=(job_id,),
                daemon=True
            )
            thread.start()

            logging_service.info(
                "BackupService",
                "CREATE_BACKUP",
                f"Backup iniciado: {job_id}",
                metadata={'backup_type': backup_type.value}
            )

            return job_id

        except Exception as e:
            logging_service.error(
                "BackupService",
                "CREATE_BACKUP_ERROR",
                f"Erro ao criar backup: {str(e)}"
            )
            raise

    def get_backup_status(self, job_id: str) -> Optional[BackupJob]:
        """
        Obter status do backup
        
        Args:
            job_id: ID do job
            
        Returns:
            BackupJob ou None se não encontrado
        """
        return self.active_jobs.get(job_id)

    def list_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Listar backups
        
        Args:
            limit: Limite de resultados
            
        Returns:
            Lista de backups
        """
        try:
            backups = []

            # Backups ativos
            for job in self.active_jobs.values():
                backups.append(asdict(job))

            # Histórico de backups
            backups.extend(self.job_history)

            # Ordenar por data (mais recentes primeiro)
            backups.sort(key=lambda x: x['created_at'], reverse=True)

            return backups[:limit]

        except Exception as e:
            logging_service.error(
                "BackupService",
                "LIST_BACKUPS_ERROR",
                f"Erro ao listar backups: {str(e)}"
            )
            return []

    def restore_backup(self, backup_file: str, restore_database: bool = True, restore_files: bool = True) -> bool:
        """
        Restaurar backup
        
        Args:
            backup_file: Arquivo de backup
            restore_database: Restaurar banco de dados
            restore_files: Restaurar arquivos
            
        Returns:
            True se restaurado com sucesso
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_file)

            if not os.path.exists(backup_path):
                raise Exception(f"Arquivo de backup não encontrado: {backup_file}")

            logging_service.info(
                "BackupService",
                "RESTORE_START",
                f"Iniciando restauração: {backup_file}"
            )

            # Extrair backup
            extract_dir = os.path.join(self.backup_dir, f"restore_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)

            try:
                with tarfile.open(backup_path, 'r:gz') as tar:
                    tar.extractall(extract_dir)

                # Restaurar banco de dados
                if restore_database:
                    db_file = os.path.join(extract_dir, 'database.sql')
                    if os.path.exists(db_file):
                        self._restore_database(db_file)

                # Restaurar arquivos
                if restore_files:
                    files_dir = os.path.join(extract_dir, 'files')
                    if os.path.exists(files_dir):
                        self._restore_files(files_dir)

                logging_service.info(
                    "BackupService",
                    "RESTORE_SUCCESS",
                    f"Restauração concluída: {backup_file}"
                )

                return True

            finally:
                # Limpar diretório temporário
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir)

        except Exception as e:
            logging_service.error(
                "BackupService",
                "RESTORE_ERROR",
                f"Erro na restauração: {str(e)}"
            )
            return False

    def delete_backup(self, backup_file: str) -> bool:
        """
        Deletar backup
        
        Args:
            backup_file: Arquivo de backup
            
        Returns:
            True se deletado com sucesso
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_file)

            if os.path.exists(backup_path):
                os.remove(backup_path)

                logging_service.info(
                    "BackupService",
                    "DELETE_BACKUP",
                    f"Backup deletado: {backup_file}"
                )

                return True

            return False

        except Exception as e:
            logging_service.error(
                "BackupService",
                "DELETE_BACKUP_ERROR",
                f"Erro ao deletar backup: {str(e)}"
            )
            return False

    def cleanup_old_backups(self) -> Dict[str, int]:
        """
        Limpar backups antigos
        
        Returns:
            Dict com estatísticas da limpeza
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.config.retention_days)
            deleted_count = 0
            freed_space_mb = 0

            # Listar arquivos de backup
            backup_files = []
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.tar.gz'):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    file_size = os.path.getsize(file_path)

                    backup_files.append({
                        'filename': filename,
                        'path': file_path,
                        'time': file_time,
                        'size': file_size
                    })

            # Ordenar por data (mais antigos primeiro)
            backup_files.sort(key=lambda x: x['time'])

            # Deletar backups antigos
            for backup_file in backup_files:
                should_delete = False

                # Deletar se muito antigo
                if backup_file['time'] < cutoff_date:
                    should_delete = True

                # Deletar se exceder limite máximo
                elif len(backup_files) - deleted_count > self.config.max_backups:
                    should_delete = True

                if should_delete:
                    try:
                        os.remove(backup_file['path'])
                        deleted_count += 1
                        freed_space_mb += backup_file['size'] / (1024 * 1024)

                        logging_service.info(
                            "BackupService",
                            "CLEANUP",
                            f"Backup antigo removido: {backup_file['filename']}"
                        )

                    except Exception as e:
                        logging_service.error(
                            "BackupService",
                            "CLEANUP_ERROR",
                            f"Erro ao remover backup: {str(e)}"
                        )

            return {
                'deleted_count': deleted_count,
                'freed_space_mb': round(freed_space_mb, 2),
                'cutoff_date': cutoff_date.isoformat()
            }

        except Exception as e:
            logging_service.error(
                "BackupService",
                "CLEANUP_ERROR",
                f"Erro na limpeza: {str(e)}"
            )
            return {
                'deleted_count': 0,
                'freed_space_mb': 0,
                'error': str(e)
            }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Obter estatísticas de backup
        
        Returns:
            Dict com estatísticas
        """
        try:
            # Contar arquivos de backup
            backup_files = []
            total_size = 0

            if os.path.exists(self.backup_dir):
                for filename in os.listdir(self.backup_dir):
                    if filename.endswith('.tar.gz'):
                        file_path = os.path.join(self.backup_dir, filename)
                        file_size = os.path.getsize(file_path)
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))

                        backup_files.append({
                            'filename': filename,
                            'size_mb': round(file_size / (1024 * 1024), 2),
                            'created_at': file_time.isoformat()
                        })

                        total_size += file_size

            # Backup mais recente
            latest_backup = None
            if backup_files:
                latest_backup = max(backup_files, key=lambda x: x['created_at'])

            # Jobs ativos
            active_jobs_count = len(self.active_jobs)

            # Estatísticas do histórico
            completed_jobs = len([j for j in self.job_history if j.get('status') == BackupStatus.COMPLETED.value])
            failed_jobs = len([j for j in self.job_history if j.get('status') == BackupStatus.FAILED.value])

            return {
                'backup_files': {
                    'count': len(backup_files),
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'latest': latest_backup,
                    'files': backup_files[:5]  # Mostrar apenas os 5 mais recentes
                },
                'jobs': {
                    'active': active_jobs_count,
                    'completed': completed_jobs,
                    'failed': failed_jobs,
                    'total_history': len(self.job_history)
                },
                'config': {
                    'enabled': self.config.enabled,
                    'backup_dir': self.config.backup_dir,
                    'retention_days': self.config.retention_days,
                    'max_backups': self.config.max_backups,
                    'schedule_hour': self.config.schedule_hour
                },
                'disk_usage': {
                    'backup_dir_size_mb': round(total_size / (1024 * 1024), 2),
                    'available_space_mb': self._get_available_space_mb()
                }
            }

        except Exception as e:
            logging_service.error(
                "BackupService",
                "GET_STATISTICS",
                f"Erro nas estatísticas: {str(e)}"
            )
            return {}

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de backup
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Verificar diretório de backup
            backup_dir_exists = os.path.exists(self.backup_dir)
            backup_dir_writable = os.access(self.backup_dir, os.W_OK) if backup_dir_exists else False

            # Verificar espaço em disco
            available_space_mb = self._get_available_space_mb()
            space_warning = available_space_mb < 1000  # Menos de 1GB

            # Verificar último backup
            last_backup_time = None
            backup_files = []

            if backup_dir_exists:
                for filename in os.listdir(self.backup_dir):
                    if filename.endswith('.tar.gz'):
                        file_path = os.path.join(self.backup_dir, filename)
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        backup_files.append(file_time)

                if backup_files:
                    last_backup_time = max(backup_files)

            # Verificar se backup está atrasado
            backup_overdue = False
            if last_backup_time:
                hours_since_backup = (datetime.utcnow() - last_backup_time).total_seconds() / 3600
                backup_overdue = hours_since_backup > 48  # Mais de 48 horas

            # Verificar jobs ativos
            stuck_jobs = []
            for job_id, job in self.active_jobs.items():
                if job.status == BackupStatus.RUNNING:
                    hours_running = (datetime.utcnow() - job.started_at).total_seconds() / 3600
                    if hours_running > 6:  # Mais de 6 horas rodando
                        stuck_jobs.append(job_id)

            # Determinar status geral
            status = "healthy"
            if not backup_dir_writable:
                status = "unhealthy"
            elif space_warning or backup_overdue or stuck_jobs:
                status = "warning"
            elif not self.config.enabled:
                status = "disabled"

            return {
                "status": status,
                "backup_directory": {
                    "path": self.backup_dir,
                    "exists": backup_dir_exists,
                    "writable": backup_dir_writable
                },
                "disk_space": {
                    "available_mb": available_space_mb,
                    "warning": space_warning
                },
                "last_backup": {
                    "time": last_backup_time.isoformat() if last_backup_time else None,
                    "overdue": backup_overdue,
                    "hours_ago": (
                        (datetime.utcnow() - last_backup_time).total_seconds() / 3600
                        if last_backup_time else None
                    )
                },
                "active_jobs": {
                    "count": len(self.active_jobs),
                    "stuck_jobs": stuck_jobs
                },
                "configuration": {
                    "enabled": self.config.enabled,
                    "retention_days": self.config.retention_days,
                    "max_backups": self.config.max_backups
                },
                "statistics": self.get_statistics(),
                "last_check": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }

    # Métodos privados auxiliares

    def _execute_backup(self, job_id: str):
        """Executar backup em background"""
        job = self.active_jobs.get(job_id)
        if not job:
            return

        try:
            # Atualizar status
            job.status = BackupStatus.RUNNING
            job.started_at = datetime.utcnow()

            # Criar arquivo de backup
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"polaris_backup_{timestamp}.tar.gz"
            backup_path = os.path.join(self.backup_dir, backup_filename)

            # Criar backup
            with tarfile.open(backup_path, 'w:gz') as tar:
                # Backup do banco de dados
                if job.metadata.get('include_database'):
                    db_backup_path = self._backup_database()
                    if db_backup_path:
                        tar.add(db_backup_path, arcname='database.sql')
                        os.remove(db_backup_path)  # Limpar arquivo temporário

                # Backup de arquivos
                if job.metadata.get('include_files'):
                    for name, path in self.backup_paths.items():
                        if os.path.exists(path):
                            tar.add(path, arcname=f'files/{name}')

                # Backup de configurações
                if job.metadata.get('include_config'):
                    config_data = {
                        'backup_config': asdict(self.config),
                        'environment_vars': dict(os.environ),
                        'timestamp': datetime.utcnow().isoformat()
                    }

                    config_file = os.path.join(self.backup_dir, 'config_temp.json')
                    with open(config_file, 'w') as f:
                        json.dump(config_data, f, indent=2)

                    tar.add(config_file, arcname='config.json')
                    os.remove(config_file)  # Limpar arquivo temporário

            # Atualizar job
            job.status = BackupStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.file_path = backup_path
            job.file_size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)

            logging_service.info(
                "BackupService",
                "BACKUP_COMPLETED",
                f"Backup concluído: {job_id}",
                metadata={
                    'file_path': backup_path,
                    'file_size_mb': job.file_size_mb
                }
            )

        except Exception as e:
            # Atualizar job com erro
            job.status = BackupStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.error_message = str(e)

            logging_service.error(
                "BackupService",
                "BACKUP_FAILED",
                f"Backup falhou: {job_id}",
                error_details={'error': str(e)}
            )

        finally:
            # Mover job para histórico
            self.job_history.append(asdict(job))
            del self.active_jobs[job_id]

            # Limitar histórico
            if len(self.job_history) > 100:
                self.job_history = self.job_history[-100:]

    def _backup_database(self) -> Optional[str]:
        """Fazer backup do banco de dados"""
        try:
            if not self.database_url:
                return None

            # Arquivo temporário para backup
            backup_file = os.path.join(self.backup_dir, f'db_backup_{int(time.time())}.sql')

            # Comando pg_dump para PostgreSQL
            if 'postgresql' in self.database_url:
                cmd = f'pg_dump "{self.database_url}" > "{backup_file}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    return backup_file
                else:
                    logging_service.error(
                        "BackupService",
                        "DB_BACKUP_ERROR",
                        f"Erro no pg_dump: {result.stderr}"
                    )

            # Para SQLite, copiar arquivo diretamente
            elif 'sqlite' in self.database_url:
                db_file = self.database_url.replace('sqlite:///', '')
                if os.path.exists(db_file):
                    shutil.copy2(db_file, backup_file)
                    return backup_file

            return None

        except Exception as e:
            logging_service.error(
                "BackupService",
                "DB_BACKUP_ERROR",
                f"Erro no backup do banco: {str(e)}"
            )
            return None

    def _restore_database(self, db_backup_file: str):
        """Restaurar banco de dados"""
        try:
            if not self.database_url or not os.path.exists(db_backup_file):
                return

            # Comando psql para PostgreSQL
            if 'postgresql' in self.database_url:
                cmd = f'psql "{self.database_url}" < "{db_backup_file}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode != 0:
                    raise Exception(f"Erro no psql: {result.stderr}")

            # Para SQLite, substituir arquivo
            elif 'sqlite' in self.database_url:
                db_file = self.database_url.replace('sqlite:///', '')
                shutil.copy2(db_backup_file, db_file)

            logging_service.info(
                "BackupService",
                "DB_RESTORE_SUCCESS",
                "Banco de dados restaurado com sucesso"
            )

        except Exception as e:
            logging_service.error(
                "BackupService",
                "DB_RESTORE_ERROR",
                f"Erro na restauração do banco: {str(e)}"
            )
            raise

    def _restore_files(self, files_backup_dir: str):
        """Restaurar arquivos"""
        try:
            for name, target_path in self.backup_paths.items():
                source_path = os.path.join(files_backup_dir, name)

                if os.path.exists(source_path):
                    # Fazer backup do diretório atual
                    if os.path.exists(target_path):
                        backup_current = f"{target_path}_backup_{int(time.time())}"
                        shutil.move(target_path, backup_current)

                    # Restaurar arquivos
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, target_path)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        shutil.copy2(source_path, target_path)

            logging_service.info(
                "BackupService",
                "FILES_RESTORE_SUCCESS",
                "Arquivos restaurados com sucesso"
            )

        except Exception as e:
            logging_service.error(
                "BackupService",
                "FILES_RESTORE_ERROR",
                f"Erro na restauração de arquivos: {str(e)}"
            )
            raise

    def _get_available_space_mb(self) -> float:
        """Obter espaço disponível em MB"""
        try:
            statvfs = os.statvfs(self.backup_dir)
            available_bytes = statvfs.f_frsize * statvfs.f_bavail
            return round(available_bytes / (1024 * 1024), 2)
        except:
            return 0.0


# Instância global do backup service
backup_service = BackupService()
