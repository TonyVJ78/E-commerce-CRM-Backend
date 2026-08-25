from django.contrib import admin

from .models import DireccionTienda, Tienda, UsuarioTienda


@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'slug', 'propietario', 'activa', 'fecha_creacion']
    list_filter = ['activa']
    search_fields = ['nombre', 'slug', 'propietario__email']
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(UsuarioTienda)
class UsuarioTiendaAdmin(admin.ModelAdmin):
    list_display = ['id', 'usuario', 'tienda', 'rol_interno', 'fecha_asignacion']
    list_filter = ['rol_interno', 'tienda']
    search_fields = ['usuario__email', 'tienda__nombre', 'rol_interno']


@admin.register(DireccionTienda)
class DireccionTiendaAdmin(admin.ModelAdmin):
    list_display = ['id', 'tienda', 'ciudad', 'direccion', 'telefono']
    list_filter = ['ciudad', 'tienda']
    search_fields = ['tienda__nombre', 'ciudad', 'direccion']

