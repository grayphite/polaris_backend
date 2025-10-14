#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
until pg_isready -h db -p 5432 -U postgres; do
  echo "Waiting for PostgreSQL..."
  sleep 2
 done

# Criar diretórios necessários
mkdir -p /app/uploads /app/indexes /app/logs

# Definir permissões
chmod 755 /app/uploads /app/indexes /app/logs

# Run migrations
flask db upgrade

# Executar comando passado como argumento
exec "$@"
