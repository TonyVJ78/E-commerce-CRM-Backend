from django.urls import path
from apps.crm.views_soporte import (
    TicketClienteCrearView,
    MisTicketsClienteListView,
    DetalleTicketView,
    ResponderTicketView,
)

urlpatterns = [
    path('tickets/', TicketClienteCrearView.as_view(), name='soporte-ticket-crear'),
    path('tickets/mis-tickets/', MisTicketsClienteListView.as_view(), name='soporte-mis-tickets'),
    path('tickets/<int:pk>/', DetalleTicketView.as_view(), name='soporte-ticket-detalle'),
    path('tickets/<int:pk>/responder/', ResponderTicketView.as_view(), name='soporte-ticket-responder'),
]
