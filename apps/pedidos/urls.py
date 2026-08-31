"""URLs del módulo de Comercio Electrónico y Ventas."""

from django.urls import path

from . import views


urlpatterns = [
    path(
        'carrito/items/',
        views.AgregarItemCarritoView.as_view(),
        name='agregar_item_carrito',
    ),
]
