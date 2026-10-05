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

api_patterns = [
    path('auth/', include('apps.usuarios.urls')),
    path('auditoria/', include('apps.usuarios.urls_auditoria')),
    path('', include('apps.usuarios.urls_accesos')),
    path('tiendas/', include('apps.tiendas.urls')),
    path('catalogo/', include('apps.catalogo.urls_cliente')),
    path('pedidos/', include('apps.pedidos.urls')),
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
