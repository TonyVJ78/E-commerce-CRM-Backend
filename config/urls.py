"""
URL configuration for Kantu Market project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.usuarios.urls')),
    path('api/tiendas/', include('apps.tiendas.urls')),
    path('api/catalogo/', include('apps.catalogo.urls')),
    path('api/pedidos/', include('apps.pedidos.urls')),
]
