from django.urls import path

from . import views


urlpatterns = [
    path(
        '<int:tienda_id>/categorias/',
        views.CategoriaListView.as_view(),
        name='categoria-list',
    ),
    path(
        '<int:tienda_id>/productos/',
        views.ProductoListCreateView.as_view(),
        name='producto-list-create',
    ),
    path(
        '<int:tienda_id>/productos/<int:producto_id>/',
        views.ProductoDetailView.as_view(),
        name='producto-detail',
    ),
]
