"""
URLs del CU07 — Bitácora. Se montan bajo /api/auditoria/.
"""

from django.urls import path

from . import views_auditoria

urlpatterns = [
    path('bitacora/', views_auditoria.BitacoraAccesoListView.as_view(), name='auditoria_bitacora'),
    path('logs/', views_auditoria.LogAuditoriaListView.as_view(), name='auditoria_logs'),
]
