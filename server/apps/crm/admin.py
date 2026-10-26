from django.contrib import admin

from .models import (
    FichaCliente,
    InteraccionCliente,
    ItemListaDeseos,
    ListaDeseos,
    Segmento,
    TicketSoporte,
    MensajeTicket,
    CampanaCarrito,
    RegistroRecuperacionCarrito,
    ReglaSegmentacion,
    SegmentoCliente,
)


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


@admin.register(TicketSoporte)
class TicketSoporteAdmin(admin.ModelAdmin):
    list_display = ['codigo_ticket', 'cliente', 'tienda', 'tipo', 'prioridad', 'estado', 'fecha_creacion']
    list_filter = ['estado', 'prioridad', 'tipo', 'tienda']
    search_fields = ['codigo_ticket', 'asunto', 'descripcion', 'cliente__email']


@admin.register(MensajeTicket)
class MensajeTicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'ticket', 'autor', 'fecha_envio']
    list_filter = ['fecha_envio']
    search_fields = ['contenido', 'autor__email', 'ticket__codigo_ticket']


@admin.register(CampanaCarrito)
class CampanaCarritoAdmin(admin.ModelAdmin):
    list_display = ['tienda', 'activo', 'horas_inactividad', 'descuento_porcentaje', 'codigo_cupon']
    list_filter = ['activo']
    search_fields = ['tienda__nombre', 'codigo_cupon']


@admin.register(RegistroRecuperacionCarrito)
class RegistroRecuperacionCarritoAdmin(admin.ModelAdmin):
    list_display = ['id', 'campana', 'carrito', 'cliente', 'recuperado', 'fecha_envio']
    list_filter = ['recuperado', 'fecha_envio']
    search_fields = ['cliente__email', 'carrito__id']


@admin.register(ReglaSegmentacion)
class ReglaSegmentacionAdmin(admin.ModelAdmin):
    list_display = ['tienda', 'dias_inactividad', 'min_compras_frecuente', 'umbral_alto_valor', 'fecha_actualizacion']
    list_filter = ['tienda']


@admin.register(SegmentoCliente)
class SegmentoClienteAdmin(admin.ModelAdmin):
    list_display = ['tienda', 'cliente', 'segmento', 'total_compras', 'monto_total_gastado', 'ultima_compra']
    list_filter = ['tienda', 'segmento']
    search_fields = ['cliente__email', 'cliente__first_name', 'cliente__last_name']
