"""
URL configuration for Kantu Market project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

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
]

urlpatterns = [
    path('', health_check, name='root_health'),
    path('health/', health_check, name='health'),
    path('admin/', admin.site.urls),
    # Matches both /api/... and direct /... in case of Vercel serverless path rewrite
    path('api/', include(api_patterns)),
    path('', include(api_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
