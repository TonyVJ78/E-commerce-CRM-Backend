#!/bin/bash
set -e

echo "Esperando a que PostgreSQL esté listo..."
while ! python -c "import socket; s = socket.socket(); s.settimeout(2); s.connect(('db', 5432)); s.close()" 2>/dev/null; do
    echo "PostgreSQL no disponible, reintentando en 2s..."
    sleep 2
done
echo "PostgreSQL listo."

echo "Generando migraciones si es necesario..."
python manage.py makemigrations --noinput

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Iniciando servidor Django..."
exec python manage.py runserver 0.0.0.0:8000
