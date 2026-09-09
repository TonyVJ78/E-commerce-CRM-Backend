from django.contrib import admin

from .models import Campana, Cupon, CuponUso, NotificacionEnviada


@admin.register(Campana)
class CampanaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'tipo', 'segmento_objetivo', 'fecha_inicio', 'fecha_fin']
    list_filter = ['tipo', 'tienda']
    search_fields = ['nombre', 'tienda__nombre']


@admin.register(Cupon)
class CuponAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'codigo', 'tipo_descuento', 'valor_descuento', 'fecha_expiracion', 'usos_maximos']
    list_filter = ['tipo_descuento', 'tienda']
    search_fields = ['codigo', 'tienda__nombre']


@admin.register(CuponUso)
class CuponUsoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cupon', 'pedido', 'fecha_uso']
    list_filter = ['tienda', 'fecha_uso']
    search_fields = ['cupon__codigo', 'pedido__id']


@admin.register(NotificacionEnviada)
class NotificacionEnviadaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'canal', 'estado_entrega', 'fecha']
    list_filter = ['canal', 'estado_entrega', 'tienda', 'fecha']
    search_fields = ['cliente__email', 'canal']
