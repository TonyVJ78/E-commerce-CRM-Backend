from django.contrib import admin

from .models import Tienda, Producto


@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'slug', 'propietario', 'activa', 'fecha_creacion']
    list_filter = ['activa']
    search_fields = ['nombre', 'slug', 'propietario__email']
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'tienda', 'precio', 'stock', 'activo', 'fecha_creacion']
    list_filter = ['activo', 'tienda']
    search_fields = ['nombre', 'tienda__nombre']