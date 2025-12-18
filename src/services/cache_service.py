"""
CacheService - Sistema de Cache

Este service gerencia cache em memória e Redis para otimizar
performance do sistema POLARIS.
"""

import os
import pickle
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Dict, List

# Imports para cache
try:
    import redis
    from redis.exceptions import ConnectionError as RedisConnectionError
except ImportError:
    redis = None
    RedisConnectionError = Exception


@dataclass
class CacheStats:
    """Estatísticas do cache"""
    total_keys: int
    memory_usage_mb: float
    hit_rate: float
    miss_rate: float
    operations_count: int
    last_cleanup: datetime


class CacheService:
    """Service para gerenciamento de cache"""

    def __init__(self):
        # Configurações
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.default_ttl = 3600  # 1 hora
        self.max_memory_cache_size = 1000  # máximo de itens em memória

        # Cache em memória (fallback)
        self.memory_cache = {}
        self.memory_cache_timestamps = {}
        self.memory_cache_ttl = {}

        # Estatísticas
        self.stats = {
            'hits': 0,
            'misses': 0,
            'operations': 0
        }

        # Cliente Redis
        self.redis_client = None
        self.redis_available = False

        # Inicializar Redis
        self._init_redis()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Obter valor do cache
        
        Args:
            key: Chave do cache
            default: Valor padrão se não encontrado
            
        Returns:
            Valor do cache ou default
        """
        try:
            self.stats['operations'] += 1

            # Tentar Redis primeiro
            if self.redis_available:
                try:
                    value = self.redis_client.get(key)
                    if value is not None:
                        self.stats['hits'] += 1
                        return pickle.loads(value)
                except Exception as e:
                    self._log_error(f"Erro no Redis get: {str(e)}")

            # Fallback para cache em memória
            if key in self.memory_cache:
                # Verificar TTL
                if self._is_memory_cache_valid(key):
                    self.stats['hits'] += 1
                    return self.memory_cache[key]
                else:
                    # Remover item expirado
                    self._remove_from_memory_cache(key)

            self.stats['misses'] += 1
            return default

        except Exception as e:
            self._log_error(f"Erro no get: {str(e)}")
            self.stats['misses'] += 1
            return default

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Definir valor no cache
        
        Args:
            key: Chave do cache
            value: Valor a ser armazenado
            ttl: Time to live em segundos (opcional)
            
        Returns:
            True se definido com sucesso
        """
        try:
            self.stats['operations'] += 1
            ttl = ttl or self.default_ttl

            # Tentar Redis primeiro
            if self.redis_available:
                try:
                    serialized_value = pickle.dumps(value)
                    self.redis_client.setex(key, ttl, serialized_value)
                    return True
                except Exception as e:
                    self._log_error(f"Erro no Redis set: {str(e)}")

            # Fallback para cache em memória
            self._set_memory_cache(key, value, ttl)
            return True

        except Exception as e:
            self._log_error(f"Erro no set: {str(e)}")
            return False

    def delete(self, key: str) -> bool:
        """
        Remover valor do cache
        
        Args:
            key: Chave do cache
            
        Returns:
            True se removido com sucesso
        """
        try:
            self.stats['operations'] += 1
            success = False

            # Remover do Redis
            if self.redis_available:
                try:
                    result = self.redis_client.delete(key)
                    success = result > 0
                except Exception as e:
                    self._log_error(f"Erro no Redis delete: {str(e)}")

            # Remover do cache em memória
            if key in self.memory_cache:
                self._remove_from_memory_cache(key)
                success = True

            return success

        except Exception as e:
            self._log_error(f"Erro no delete: {str(e)}")
            return False

    def exists(self, key: str) -> bool:
        """
        Verificar se chave existe no cache
        
        Args:
            key: Chave do cache
            
        Returns:
            True se existe
        """
        try:
            # Verificar Redis
            if self.redis_available:
                try:
                    return self.redis_client.exists(key) > 0
                except Exception as e:
                    self._log_error(f"Erro no Redis exists: {str(e)}")

            # Verificar cache em memória
            return key in self.memory_cache and self._is_memory_cache_valid(key)

        except Exception as e:
            self._log_error(f"Erro no exists: {str(e)}")
            return False

    def clear(self, pattern: str = None) -> bool:
        """
        Limpar cache
        
        Args:
            pattern: Padrão de chaves para limpar (opcional)
            
        Returns:
            True se limpo com sucesso
        """
        try:
            self.stats['operations'] += 1

            # Limpar Redis
            if self.redis_available:
                try:
                    if pattern:
                        keys = self.redis_client.keys(pattern)
                        if keys:
                            self.redis_client.delete(*keys)
                    else:
                        self.redis_client.flushdb()
                except Exception as e:
                    self._log_error(f"Erro no Redis clear: {str(e)}")

            # Limpar cache em memória
            if pattern:
                # Remover chaves que correspondem ao padrão
                import fnmatch
                keys_to_remove = [
                    key for key in self.memory_cache.keys()
                    if fnmatch.fnmatch(key, pattern)
                ]
                for key in keys_to_remove:
                    self._remove_from_memory_cache(key)
            else:
                # Limpar tudo
                self.memory_cache.clear()
                self.memory_cache_timestamps.clear()
                self.memory_cache_ttl.clear()

            return True

        except Exception as e:
            self._log_error(f"Erro no clear: {str(e)}")
            return False

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Incrementar valor numérico no cache
        
        Args:
            key: Chave do cache
            amount: Quantidade a incrementar
            
        Returns:
            Novo valor ou None se erro
        """
        try:
            self.stats['operations'] += 1

            # Tentar Redis primeiro
            if self.redis_available:
                try:
                    return self.redis_client.incrby(key, amount)
                except Exception as e:
                    self._log_error(f"Erro no Redis increment: {str(e)}")

            # Fallback para cache em memória
            current_value = self.get(key, 0)
            if isinstance(current_value, (int, float)):
                new_value = current_value + amount
                self.set(key, new_value)
                return new_value

            return None

        except Exception as e:
            self._log_error(f"Erro no increment: {str(e)}")
            return None

    def get_multiple(self, keys: List[str]) -> Dict[str, Any]:
        """
        Obter múltiplos valores do cache
        
        Args:
            keys: Lista de chaves
            
        Returns:
            Dict com chaves e valores encontrados
        """
        try:
            self.stats['operations'] += len(keys)
            result = {}

            # Tentar Redis primeiro
            if self.redis_available:
                try:
                    values = self.redis_client.mget(keys)
                    for i, value in enumerate(values):
                        if value is not None:
                            result[keys[i]] = pickle.loads(value)
                            self.stats['hits'] += 1
                        else:
                            self.stats['misses'] += 1
                    return result
                except Exception as e:
                    self._log_error(f"Erro no Redis mget: {str(e)}")

            # Fallback para cache em memória
            for key in keys:
                value = self.get(key)
                if value is not None:
                    result[key] = value

            return result

        except Exception as e:
            self._log_error(f"Erro no get_multiple: {str(e)}")
            return {}

    def set_multiple(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        """
        Definir múltiplos valores no cache
        
        Args:
            mapping: Dict com chaves e valores
            ttl: Time to live em segundos (opcional)
            
        Returns:
            True se definido com sucesso
        """
        try:
            self.stats['operations'] += len(mapping)
            ttl = ttl or self.default_ttl

            # Tentar Redis primeiro
            if self.redis_available:
                try:
                    pipe = self.redis_client.pipeline()
                    for key, value in mapping.items():
                        serialized_value = pickle.dumps(value)
                        pipe.setex(key, ttl, serialized_value)
                    pipe.execute()
                    return True
                except Exception as e:
                    self._log_error(f"Erro no Redis mset: {str(e)}")

            # Fallback para cache em memória
            for key, value in mapping.items():
                self._set_memory_cache(key, value, ttl)

            return True

        except Exception as e:
            self._log_error(f"Erro no set_multiple: {str(e)}")
            return False

    def get_stats(self) -> CacheStats:
        """
        Obter estatísticas do cache
        
        Returns:
            CacheStats com estatísticas
        """
        try:
            total_keys = 0
            memory_usage_mb = 0

            # Estatísticas do Redis
            if self.redis_available:
                try:
                    info = self.redis_client.info('memory')
                    memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
                    total_keys = self.redis_client.dbsize()
                except Exception as e:
                    self._log_error(f"Erro nas estatísticas Redis: {str(e)}")

            # Adicionar estatísticas do cache em memória
            total_keys += len(self.memory_cache)

            # Calcular uso de memória do cache em memória (estimativa)
            memory_cache_size = 0
            for key, value in self.memory_cache.items():
                try:
                    memory_cache_size += len(pickle.dumps(value))
                    memory_cache_size += len(key.encode('utf-8'))
                except:
                    pass

            memory_usage_mb += memory_cache_size / (1024 * 1024)

            # Calcular taxas
            total_operations = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_operations * 100) if total_operations > 0 else 0
            miss_rate = (self.stats['misses'] / total_operations * 100) if total_operations > 0 else 0

            return CacheStats(
                total_keys=total_keys,
                memory_usage_mb=round(memory_usage_mb, 2),
                hit_rate=round(hit_rate, 2),
                miss_rate=round(miss_rate, 2),
                operations_count=self.stats['operations'],
                last_cleanup=datetime.utcnow()
            )

        except Exception as e:
            self._log_error(f"Erro nas estatísticas: {str(e)}")
            return CacheStats(
                total_keys=0,
                memory_usage_mb=0,
                hit_rate=0,
                miss_rate=0,
                operations_count=0,
                last_cleanup=datetime.utcnow()
            )

    def cleanup_expired(self) -> int:
        """
        Limpar itens expirados do cache em memória
        
        Returns:
            Número de itens removidos
        """
        try:
            removed_count = 0
            current_time = time.time()

            # Identificar chaves expiradas
            expired_keys = []
            for key in list(self.memory_cache.keys()):
                if not self._is_memory_cache_valid(key):
                    expired_keys.append(key)

            # Remover chaves expiradas
            for key in expired_keys:
                self._remove_from_memory_cache(key)
                removed_count += 1

            return removed_count

        except Exception as e:
            self._log_error(f"Erro na limpeza: {str(e)}")
            return 0

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde do sistema de cache
        
        Returns:
            Dict com status do sistema
        """
        try:
            # Testar Redis
            redis_status = "unavailable"
            redis_info = {}

            if self.redis_available:
                try:
                    self.redis_client.ping()
                    redis_status = "healthy"
                    redis_info = {
                        'connected': True,
                        'version': self.redis_client.info().get('redis_version', 'unknown')
                    }
                except Exception as e:
                    redis_status = "unhealthy"
                    redis_info = {'error': str(e)}

            # Testar cache em memória
            memory_cache_status = "healthy"
            try:
                test_key = f"health_check_{int(time.time())}"
                self._set_memory_cache(test_key, "test_value", 60)
                if self.memory_cache.get(test_key) != "test_value":
                    memory_cache_status = "unhealthy"
                self._remove_from_memory_cache(test_key)
            except Exception as e:
                memory_cache_status = "unhealthy"

            # Estatísticas
            stats = self.get_stats()

            # Status geral
            overall_status = "healthy"
            if redis_status == "unhealthy" and memory_cache_status == "unhealthy":
                overall_status = "unhealthy"
            elif redis_status == "unavailable":
                overall_status = "degraded"

            return {
                "status": overall_status,
                "redis": {
                    "status": redis_status,
                    "info": redis_info,
                    "url": self.redis_url
                },
                "memory_cache": {
                    "status": memory_cache_status,
                    "size": len(self.memory_cache),
                    "max_size": self.max_memory_cache_size
                },
                "statistics": {
                    "total_keys": stats.total_keys,
                    "memory_usage_mb": stats.memory_usage_mb,
                    "hit_rate": stats.hit_rate,
                    "miss_rate": stats.miss_rate,
                    "operations_count": stats.operations_count
                },
                "config": {
                    "default_ttl": self.default_ttl,
                    "max_memory_cache_size": self.max_memory_cache_size
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

    def _init_redis(self):
        """Inicializar conexão Redis"""
        if redis is None:
            self._log_error("Redis não disponível")
            return

        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=False,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )

            # Testar conexão
            self.redis_client.ping()
            self.redis_available = True

        except Exception as e:
            self._log_error(f"Erro na conexão Redis: {str(e)}")
            self.redis_available = False

    def _set_memory_cache(self, key: str, value: Any, ttl: int):
        """Definir valor no cache em memória"""
        # Verificar limite de tamanho
        if len(self.memory_cache) >= self.max_memory_cache_size:
            # Remover item mais antigo
            oldest_key = min(
                self.memory_cache_timestamps.keys(),
                key=lambda k: self.memory_cache_timestamps[k]
            )
            self._remove_from_memory_cache(oldest_key)

        # Adicionar novo item
        current_time = time.time()
        self.memory_cache[key] = value
        self.memory_cache_timestamps[key] = current_time
        self.memory_cache_ttl[key] = current_time + ttl

    def _remove_from_memory_cache(self, key: str):
        """Remover item do cache em memória"""
        self.memory_cache.pop(key, None)
        self.memory_cache_timestamps.pop(key, None)
        self.memory_cache_ttl.pop(key, None)

    def _is_memory_cache_valid(self, key: str) -> bool:
        """Verificar se item do cache em memória é válido"""
        if key not in self.memory_cache_ttl:
            return False

        return time.time() < self.memory_cache_ttl[key]

    def _log_error(self, error_msg: str):
        """Log de erro"""
        try:
            print(f"[ERROR] CacheService: {error_msg}")
        except:
            print(f"[ERROR] CacheService: {error_msg}")


# Instância global do cache service
cache_service = CacheService()
