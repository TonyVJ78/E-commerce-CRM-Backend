"""
URLs del módulo de Usuarios.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('registro/', views.RegistroView.as_view(), name='registro'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset-confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
]
