from django.contrib import admin

from .models import GastoOperativo, TipoCambio


@admin.register(GastoOperativo)
class GastoOperativoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'categoria', 'monto', 'fecha', 'registrado_por']
    list_filter = ['categoria', 'tienda', 'fecha']
    search_fields = ['descripcion', 'tienda__nombre']


@admin.register(TipoCambio)
class TipoCambioAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'usd_bob', 'ufv_bob', 'fuente', 'obtenido_en']
    ordering = ['-fecha']
