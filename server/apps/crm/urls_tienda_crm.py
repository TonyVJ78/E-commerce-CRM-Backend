from django.urls import path
from apps.crm.views_soporte import (
    TiendaTicketsListView,
    TiendaActualizarEstadoTicketView,
)
from apps.crm.views_campana import (
    TiendaCampanaCarritoView,
    TiendaCarritosAbandonadosListView,
    TiendaDispararPruebaCampanaView,
)

urlpatterns = [
    # CU-26: Gestion de Tickets y Reclamos para la Tienda
    path('<int:tienda_id>/tickets/', TiendaTicketsListView.as_view(), name='tienda-tickets-list'),
    path('<int:tienda_id>/tickets/<int:pk>/estado/', TiendaActualizarEstadoTicketView.as_view(), name='tienda-ticket-estado'),

    # CU-27: Campana de Carrito Abandonado
    path('<int:tienda_id>/campana-carrito/', TiendaCampanaCarritoView.as_view(), name='tienda-campana-carrito'),
    path('<int:tienda_id>/carritos-abandonados/', TiendaCarritosAbandonadosListView.as_view(), name='tienda-carritos-abandonados'),
    path('<int:tienda_id>/campana-carrito/disparar-prueba/', TiendaDispararPruebaCampanaView.as_view(), name='tienda-campana-disparar-prueba'),
]
