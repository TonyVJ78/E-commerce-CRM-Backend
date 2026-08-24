from django.contrib import admin

from .models import BitacoraAcceso, Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre']


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'email', 'first_name', 'last_name', 'rol', 'activo', 'fecha_registro']
    list_filter = ['activo', 'rol']
    search_fields = ['email', 'first_name', 'last_name']


@admin.register(BitacoraAcceso)
class BitacoraAccesoAdmin(admin.ModelAdmin):
    list_display = ['id', 'usuario', 'fecha', 'ip', 'dispositivo']
    list_filter = ['fecha']
    search_fields = ['usuario__email', 'ip']
