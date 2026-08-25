from django.contrib import admin

from .models import (
    Carrito,
    DireccionEnvio,
    Envio,
    HistorialEstadoPedido,
    ItemCarrito,
    ItemPedido,
    MetodoPago,
    Pago,
    Pedido,
    Resena,
)


@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['id', 'cliente', 'tienda', 'fecha_creacion']
    list_filter = ['tienda']
    search_fields = ['cliente__email', 'tienda__nombre']


@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'carrito', 'variante', 'cantidad']
    list_filter = ['tienda']
    search_fields = ['carrito__cliente__email', 'variante__nombre_variante']


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre']
    search_fields = ['nombre']


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ['id', 'cliente', 'tienda', 'estado_actual', 'subtotal', 'total', 'fecha']
    list_filter = ['estado_actual', 'tienda', 'fecha']
    search_fields = ['id', 'cliente__email', 'tienda__nombre']


@admin.register(ItemPedido)
class ItemPedidoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'pedido', 'variante', 'cantidad', 'precio_unitario']
    list_filter = ['tienda']
    search_fields = ['pedido__id', 'variante__nombre_variante']


@admin.register(HistorialEstadoPedido)
class HistorialEstadoPedidoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'pedido', 'estado', 'fecha']
    list_filter = ['estado', 'tienda', 'fecha']
    search_fields = ['pedido__id']


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'pedido', 'metodo_pago', 'monto', 'estado', 'fecha']
    list_filter = ['estado', 'metodo_pago', 'tienda', 'fecha']
    search_fields = ['pedido__id', 'referencia_transaccion']


@admin.register(DireccionEnvio)
class DireccionEnvioAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'ciudad', 'direccion', 'es_predeterminada']
    list_filter = ['ciudad', 'es_predeterminada', 'tienda']
    search_fields = ['cliente__email', 'direccion', 'ciudad']


@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'pedido', 'transportista', 'numero_seguimiento', 'fecha_envio', 'fecha_entrega']
    list_filter = ['transportista', 'tienda']
    search_fields = ['pedido__id', 'numero_seguimiento']


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'producto', 'calificacion', 'fecha']
    list_filter = ['calificacion', 'tienda', 'fecha']
    search_fields = ['cliente__email', 'producto__nombre', 'comentario']
