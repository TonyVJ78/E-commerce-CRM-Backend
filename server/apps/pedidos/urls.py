"""URLs del módulo de Comercio Electrónico y Ventas."""

from django.urls import path

from . import views


urlpatterns = [
    path('carrito/', views.CarritoDetalleView.as_view(), name='carrito_detalle'),
    path(
        'carrito/items/',
        views.AgregarItemCarritoView.as_view(),
        name='agregar_item_carrito',
    ),
    path(
        'carrito/items/<int:item_id>/',
        views.ItemCarritoDetailView.as_view(),
        name='item_carrito_detalle',
    ),
    path(
        'carrito/checkout/',
        views.CheckoutView.as_view(),
        name='carrito_checkout',
    ),
]


