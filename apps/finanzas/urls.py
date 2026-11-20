from django.urls import path

from . import views

urlpatterns = [
    path('tipo-cambio/', views.TipoCambioView.as_view(), name='tipo-cambio'),
    path('tipo-cambio/actualizar/', views.ActualizarTipoCambioView.as_view(), name='tipo-cambio-actualizar'),
    path('tiendas/<int:tienda_id>/gastos/', views.GastoListCreateView.as_view(), name='gastos-list-create'),
    path('tiendas/<int:tienda_id>/gastos/totales/', views.GastoTotalesView.as_view(), name='gastos-totales'),
    path('tiendas/<int:tienda_id>/gastos/<int:pk>/', views.GastoDetailView.as_view(), name='gastos-detail'),
]
