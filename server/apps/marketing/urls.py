from django.urls import path
from .views import CuponesClienteView, ValidarCuponView

urlpatterns = [
    path('cupones/', CuponesClienteView.as_view(), name='marketing-cupones-cliente'),
    path('cupones/validar/', ValidarCuponView.as_view(), name='marketing-validar-cupon'),
]
