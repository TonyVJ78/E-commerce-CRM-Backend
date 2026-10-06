from django.contrib import admin

from .models import BitacoraAcceso, LogAuditoria, Permiso, Rol, RolPermiso, Usuario


class RolPermisoInline(admin.TabularInline):
    model = RolPermiso
    extra = 1
    autocomplete_fields = ['permiso']


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre']
    inlines = [RolPermisoInline]


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
    list_display = ['id', 'usuario', 'email_intento', 'exitoso', 'motivo', 'fecha', 'ip', 'dispositivo']
    list_filter = ['exitoso', 'fecha']
    search_fields = ['usuario__email', 'email_intento', 'ip']


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ['id', 'usuario', 'tabla_afectada', 'registro_id', 'accion', 'fecha']
    list_filter = ['accion', 'tabla_afectada', 'fecha']
    search_fields = ['tabla_afectada', 'usuario__email']


class RespaldoBaseDatos(Usuario):
    """Proxy model sin tabla física para exponer la gestión de respaldos en el menú de Django Admin."""
    class Meta:
        proxy = True
        verbose_name = 'Copia de Seguridad (Backup)'
        verbose_name_plural = 'Copias de Seguridad (Backups)'


@admin.register(RespaldoBaseDatos)
class RespaldoBaseDatosAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('admin_backups_dashboard')

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

