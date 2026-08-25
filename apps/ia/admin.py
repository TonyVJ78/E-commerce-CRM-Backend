from django.contrib import admin

from .models import EventoUsuario, Recomendacion, ReporteGenerado


@admin.register(EventoUsuario)
class EventoUsuarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'producto', 'tipo_evento', 'fecha']
    list_filter = ['tipo_evento', 'tienda', 'fecha']
    search_fields = ['cliente__email', 'producto__nombre', 'tipo_evento']


@admin.register(Recomendacion)
class RecomendacionAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'cliente', 'producto', 'score', 'fecha_generada']
    list_filter = ['tienda', 'fecha_generada']
    search_fields = ['cliente__email', 'producto__nombre']


@admin.register(ReporteGenerado)
class ReporteGeneradoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'generado_por_usuario', 'tipo_reporte', 'formato', 'fecha_generacion']
    list_filter = ['tipo_reporte', 'formato', 'tienda', 'fecha_generacion']
    search_fields = ['tipo_reporte', 'generado_por_usuario__email', 'tienda__nombre']
