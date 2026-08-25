from django.contrib import admin

from .models import FichaCliente, InteraccionCliente, ItemListaDeseos, ListaDeseos, Segmento


@admin.register(Segmento)
class SegmentoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'criterio']
    list_filter = ['tienda']
    search_fields = ['nombre', 'criterio', 'tienda__nombre']


@admin.register(FichaCliente)
class FichaClienteAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'segmento', 'fecha_actualizacion']
    list_filter = ['tienda', 'segmento']
    search_fields = ['cliente__email', 'tienda__nombre']


@admin.register(InteraccionCliente)
class InteraccionClienteAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'ficha_cliente', 'tipo', 'estado', 'fecha']
    list_filter = ['tipo', 'estado', 'tienda', 'fecha']
    search_fields = ['mensaje', 'ficha_cliente__cliente__email']


@admin.register(ListaDeseos)
class ListaDeseosAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'ficha_cliente', 'fecha_creacion']
    list_filter = ['tienda']
    search_fields = ['ficha_cliente__cliente__email', 'tienda__nombre']


@admin.register(ItemListaDeseos)
class ItemListaDeseosAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'lista_deseos', 'producto']
    list_filter = ['tienda']
    search_fields = ['producto__nombre', 'lista_deseos__ficha_cliente__cliente__email']
