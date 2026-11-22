from django.contrib import admin

from .models import (
    EntrenamientoModelo,
    PrediccionCompra,
    PrediccionVenta,
    RiesgoAbandono,
)


@admin.register(PrediccionVenta)
class PrediccionVentaAdmin(admin.ModelAdmin):
    list_display = [
        'tienda', 'periodo_inicio', 'periodo_fin',
        'horizonte_dias', 'valor_previsto', 'mae', 'rmse',
        'fecha_entrenamiento', 'version_modelo',
    ]
    list_filter = ['tienda', 'fecha_entrenamiento']
    search_fields = ['tienda__nombre']


@admin.register(RiesgoAbandono)
class RiesgoAbandonoAdmin(admin.ModelAdmin):
    list_display = [
        'cliente', 'tienda', 'probabilidad_abandono',
        'nivel_riesgo', 'fecha_scoring', 'version_modelo',
    ]
    list_filter = ['nivel_riesgo', 'tienda', 'fecha_scoring']
    search_fields = ['cliente__email', 'tienda__nombre']


@admin.register(PrediccionCompra)
class PrediccionCompraAdmin(admin.ModelAdmin):
    list_display = [
        'cliente', 'tienda', 'probabilidad_compra',
        'horizonte_dias', 'fecha_prediccion', 'version_modelo',
    ]
    list_filter = ['tienda', 'fecha_prediccion']
    search_fields = ['cliente__email', 'tienda__nombre']


@admin.register(EntrenamientoModelo)
class EntrenamientoModeloAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_modelo', 'estado', 'fecha_inicio',
        'fecha_fin', 'usuario_ejecutor',
    ]
    list_filter = ['tipo_modelo', 'estado', 'fecha_inicio']
    search_fields = ['usuario_ejecutor__email']
