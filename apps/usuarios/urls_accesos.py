"""
URLs del CU07 — Gestionar roles y permisos. Se montan bajo /api/.
"""

from django.urls import path

from . import views_accesos

urlpatterns = [
    path('roles/', views_accesos.RolListCreateView.as_view(), name='rol_list_create'),
    path('roles/<int:pk>/', views_accesos.RolDetailView.as_view(), name='rol_detail'),
    path('roles/<int:pk>/permisos/', views_accesos.RolPermisosView.as_view(), name='rol_permisos'),
    path('permisos/', views_accesos.PermisoListView.as_view(), name='permiso_list'),
    path('usuarios/', views_accesos.UsuarioAdminListView.as_view(), name='usuario_admin_list'),
    path('usuarios/<int:pk>/', views_accesos.UsuarioAdminDetailView.as_view(), name='usuario_admin_detail'),
]
