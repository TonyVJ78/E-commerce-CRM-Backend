"""
URL configuration for Kantu Market project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.usuarios.admin_backup_views import (
    admin_backup_download_view,
    admin_backups_dashboard_view,
)

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "Kantu Market API",
        "database": "Neon Cloud PostgreSQL",
        "version": "1.0.0"
    })

from apps.marketing.views_notificaciones import DispositivoView

api_patterns = [
    path('usuarios/dispositivos/', DispositivoView.as_view(), name='registrar-dispositivo-push'),
    path('health/', health_check, name='api_health'),
    path('auth/', include('apps.usuarios.urls')),
    path('auditoria/', include('apps.usuarios.urls_auditoria')),
    path('admin/backups/', include('apps.usuarios.urls_backup_api')),
    path('', include('apps.usuarios.urls_accesos')),
    path('tiendas/', include('apps.tiendas.urls')),
    # Gestion de pedidos recibidos por tienda (CU-22)
    path('tiendas/', include('apps.pedidos.urls_empresa')),
    path('tiendas/', include('apps.crm.urls_tienda_crm')),
    path('soporte/', include('apps.crm.urls_soporte')),
    path('marketing/', include('apps.marketing.urls')),
    path('tiendas/', include('apps.marketing.urls_tienda')),
    path('catalogo/', include('apps.catalogo.urls_cliente')),
    path('pedidos/', include('apps.pedidos.urls')),
    # Chatbot de recomendaciones (Claude) y recomendaciones personalizadas (CU-14)
    path('ia/', include('apps.ia.urls')),
    path('recomendaciones/', include('apps.ia.urls')),
]

urlpatterns = [
    path('', health_check, name='root_health'),
    path('health/', health_check, name='health'),
    # Django Admin Backups (Panel y Descarga Directa para Superadministrador)
    path('admin/backups/', admin_backups_dashboard_view, name='admin_backups_dashboard'),
    path('admin/backups/descargar/<str:filename>/', admin_backup_download_view, name='admin_backup_download'),
    path('admin/', admin.site.urls),
    # Matches both /api/... and direct /... in case of Vercel serverless path rewrite
    path('api/', include(api_patterns)),
    path('', include(api_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
