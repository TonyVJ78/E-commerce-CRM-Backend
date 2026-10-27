from django.urls import path
from .views import CuponesClienteView, ValidarCuponView

from .views_notificaciones import BandejaView, LeerNotificacionView

urlpatterns = [
    path('notificaciones/', BandejaView.as_view(), name='marketing-bandeja'),
    path('notificaciones/<int:pk>/', LeerNotificacionView.as_view(), name='marketing-leer'),
    path('cupones/', CuponesClienteView.as_view(), name='marketing-cupones-cliente'),
    path('cupones/validar/', ValidarCuponView.as_view(), name='marketing-validar-cupon'),
]
