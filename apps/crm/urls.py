from django.urls import path
from . import views_api

urlpatterns = [
    path('clientes/', views_api.CrmClientesListView.as_view(), name='crm-clientes-list'),
    path('clientes/<int:cliente_id>/', views_api.CrmClienteDetalleView.as_view(), name='crm-cliente-detail'),
    path('clientes/<int:cliente_id>/interacciones/', views_api.CrmInteraccionesView.as_view(), name='crm-interacciones'),
]
