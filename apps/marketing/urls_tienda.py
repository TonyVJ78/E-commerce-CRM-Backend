from django.urls import path
from .views import CuponesTiendaView, CuponTiendaDetalleView

urlpatterns = [
    path('<int:tienda_id>/cupones/', CuponesTiendaView.as_view(), name='tienda-cupones'),
    path('<int:tienda_id>/cupones/<int:pk>/', CuponTiendaDetalleView.as_view(), name='tienda-cupon-detalle'),
]
