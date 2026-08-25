from django.contrib import admin

from .models import BitacoraAcceso, LogAuditoria, Permiso, Rol, RolPermiso, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre']


@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ['id', 'codigo', 'nombre']
    search_fields = ['codigo', 'nombre']


@admin.register(RolPermiso)
class RolPermisoAdmin(admin.ModelAdmin):
    list_display = ['id', 'rol', 'permiso']
    list_filter = ['rol']


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


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'usuario', 'tabla_afectada', 'registro_id', 'accion', 'fecha']
    list_filter = ['accion', 'tabla_afectada', 'fecha']
    search_fields = ['tabla_afectada', 'usuario__email']

