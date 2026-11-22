from apps.catalogo.services import recalcular_precios_usd
from .bloqueo import bloquear_cotizacion
from .tipo_cambio import tipo_cambio_vigente
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
    readonly_fields = ['brl_bob', 'brl_fuente', 'brl_obtenido_en']

    def save_model(self, request, obj, form, change):
        with bloquear_cotizacion():
            super().save_model(request, obj, form, change)
            vigente = tipo_cambio_vigente()
            if vigente:
                recalcular_precios_usd(vigente.usd_bob)
