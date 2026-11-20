"""URLs de CU-22 (gestión de pedidos recibidos), montadas bajo /api/tiendas/."""

from django.urls import path

from . import views_empresa, views_satisfaccion


urlpatterns = [
    path(
        '<int:tienda_id>/pedidos/',
        views_empresa.PedidosTiendaListView.as_view(),
        name='pedidos-tienda-list',
    ),
    path(
        '<int:tienda_id>/pedidos/<int:pedido_id>/',
        views_empresa.PedidoTiendaDetailView.as_view(),
        name='pedido-tienda-detail',
    ),
    path(
        '<int:tienda_id>/pedidos/<int:pedido_id>/estado/',
        views_empresa.PedidoTiendaEstadoView.as_view(),
        name='pedido-tienda-estado',
    ),
    path(
        '<int:tienda_id>/satisfaccion/',
        views_satisfaccion.SatisfaccionTiendaView.as_view(),
        name='satisfaccion-tienda',
    ),
    path(
        '<int:tienda_id>/satisfaccion/resumen-ia/',
        views_satisfaccion.ResumenComentariosIaView.as_view(),
        name='satisfaccion-tienda-resumen-ia',
    ),
]
