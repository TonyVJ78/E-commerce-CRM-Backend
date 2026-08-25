from django.contrib import admin

from .models import (
    Atributo,
    Categoria,
    Etiqueta,
    ImagenProducto,
    Inventario,
    Producto,
    ProductoEtiqueta,
    VarianteAtributo,
    VarianteProducto,
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'categoria_padre']
    list_filter = ['tienda']
    search_fields = ['nombre', 'tienda__nombre']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre', 'categoria', 'precio_base', 'sku', 'activo']
    list_filter = ['activo', 'tienda', 'categoria']
    search_fields = ['nombre', 'sku', 'tienda__nombre']


@admin.register(VarianteProducto)
class VarianteProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'producto', 'nombre_variante', 'precio_adicional', 'sku_variante']
    list_filter = ['tienda']
    search_fields = ['nombre_variante', 'sku_variante', 'producto__nombre']


@admin.register(Atributo)
class AtributoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre']
    list_filter = ['tienda']
    search_fields = ['nombre', 'tienda__nombre']


@admin.register(VarianteAtributo)
class VarianteAtributoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'variante', 'atributo', 'valor']
    list_filter = ['tienda', 'atributo']
    search_fields = ['valor', 'variante__nombre_variante', 'atributo__nombre']


@admin.register(ImagenProducto)
class ImagenProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'producto', 'url', 'orden']
    list_filter = ['tienda']
    search_fields = ['producto__nombre', 'url']


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'variante', 'stock', 'umbral_minimo']
    list_filter = ['tienda']
    search_fields = ['variante__nombre_variante', 'variante__producto__nombre']


@admin.register(Etiqueta)
class EtiquetaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'nombre']
    list_filter = ['tienda']
    search_fields = ['nombre', 'tienda__nombre']


@admin.register(ProductoEtiqueta)
class ProductoEtiquetaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'producto', 'etiqueta']
    list_filter = ['tienda', 'etiqueta']
    search_fields = ['producto__nombre', 'etiqueta__nombre']
