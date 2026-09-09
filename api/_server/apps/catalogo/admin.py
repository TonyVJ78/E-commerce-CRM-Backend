from django.contrib import admin

from .models import Categoria, Producto, Variante


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'categoria_padre']
    list_filter = ['tienda']
    search_fields = ['nombre', 'tienda__nombre']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'categoria', 'activo']
    list_filter = ['activo', 'tienda', 'categoria']
    search_fields = ['nombre', 'slug', 'tienda__nombre']


@admin.register(Variante)
class VarianteAdmin(admin.ModelAdmin):
    list_display = ['id', 'producto', 'nombre', 'sku', 'precio', 'stock', 'activa']
    list_filter = ['activa', 'producto__tienda']
    search_fields = ['nombre', 'sku', 'producto__nombre']
