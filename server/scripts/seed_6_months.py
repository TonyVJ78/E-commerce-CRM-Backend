"""
Script ejecutable para poblar 6 meses de historial continuo en Kantu Market.
Permite ejecutar directamente:
    python server/scripts/seed_6_months.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command

if __name__ == '__main__':
    purge = '--purge' in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != '--purge']
    pedidos = int(args[0]) if len(args) > 0 and args[0].isdigit() else 120
    eventos = int(args[1]) if len(args) > 1 and args[1].isdigit() else 350
    call_command('seed_6_months', purge=purge, pedidos=pedidos, eventos=eventos, stock=10000)
