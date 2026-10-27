from django.urls import path
from apps.usuarios.views_backup_api import (
    BackupListApiView,
    BackupGenerarApiView,
    BackupDescargarApiView,
    BackupAutomatizacionApiView,
)

urlpatterns = [
    path('', BackupListApiView.as_view(), name='api_backups_list'),
    path('generar/', BackupGenerarApiView.as_view(), name='api_backups_generar'),
    path('descargar/', BackupDescargarApiView.as_view(), name='api_backups_descargar'),
    path('automatizacion/', BackupAutomatizacionApiView.as_view(), name='api_backups_automatizacion'),
]
