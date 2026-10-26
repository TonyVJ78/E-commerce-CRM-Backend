"""Persistent inbox first; external delivery only after database commit."""
import logging
from threading import Lock
from django.conf import settings
from django.db import transaction
from .models import DispositivoPush, NotificacionEnviada

logger = logging.getLogger(__name__)
_firebase_lock = Lock()


def crear_notificacion(*, tienda, cliente, titulo, mensaje, tipo, datos, clave):
    payload = {str(k): str(v) for k, v in datos.items()}
    payload.update(tipo=tipo, tienda_id=str(tienda.pk))
    obj, creada = NotificacionEnviada.objects.get_or_create(clave_evento=clave,
        defaults=dict(tienda=tienda, cliente=cliente, titulo=titulo[:150], mensaje=mensaje,
                      tipo=tipo, datos=payload, canal='app', estado_entrega='pendiente'))
    if creada:
        transaction.on_commit(lambda: entregar_notificacion(obj.pk), robust=True)
    return obj, creada


def _firebase_app():
    import firebase_admin
    from firebase_admin import credentials
    with _firebase_lock:
        try:
            return firebase_admin.get_app('kantu-marketing')
        except ValueError:
            path = settings.FIREBASE_CREDENTIALS_FILE
            cred = credentials.Certificate(path) if path else credentials.ApplicationDefault()
            return firebase_admin.initialize_app(cred, name='kantu-marketing')


def entregar_notificacion(pk):
    obj = NotificacionEnviada.objects.get(pk=pk)
    if obj.estado_entrega in ('enviado', 'parcial'):
        return
    dispositivos = DispositivoPush.objects.filter(usuario=obj.cliente, activo=True)
    if not settings.FCM_ENABLED or not dispositivos.exists():
        NotificacionEnviada.objects.filter(pk=pk).update(estado_entrega='solo_bandeja')
        return
    try:
        from firebase_admin import messaging
        app = _firebase_app()
    except Exception:
        NotificacionEnviada.objects.filter(pk=pk).update(estado_entrega='sin_configuracion')
        logger.warning('Firebase no disponible para notificacion %s', pk)
        return
    enviados = fallidos = 0
    for dispositivo in dispositivos:
        try:
            messaging.send(messaging.Message(token=dispositivo.token,
                notification=messaging.Notification(title=obj.titulo, body=obj.mensaje),
                data={**obj.datos, 'notificacion_id': str(obj.pk), 'cliente_id': str(obj.cliente_id)}), app=app)
            enviados += 1
        except messaging.UnregisteredError:
            dispositivo.activo = False
            dispositivo.save(update_fields=['activo'])
            fallidos += 1
        except Exception:
            fallidos += 1
            logger.warning('Entrega push fallida para notificacion %s', pk)
    estado = 'parcial' if enviados and fallidos else 'enviado' if enviados else 'fallido'
    NotificacionEnviada.objects.filter(pk=pk).update(estado_entrega=estado, canal='app/push')


def notificar_cupon(cupon, *, dry_run=False):
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from .cupones import es_destinatario
    hoy = timezone.localdate()
    if not (cupon.activo and cupon.tienda.activa and cupon.fecha_inicio <= hoy <= cupon.fecha_expiracion):
        return 0
    # A promotion concerns customers who have interacted with this store only.
    from apps.crm.models import FichaCliente
    from apps.pedidos.models import Pedido, Carrito
    ids = set(FichaCliente.objects.filter(tienda=cupon.tienda).values_list('cliente_id', flat=True))
    ids.update(Pedido.objects.filter(tienda=cupon.tienda).values_list('cliente_id', flat=True))
    ids.update(Carrito.objects.filter(tienda=cupon.tienda).values_list('cliente_id', flat=True))
    total = 0
    for cliente in get_user_model().objects.filter(pk__in=ids, is_active=True, activo=True, rol__nombre='cliente'):
        if es_destinatario(cupon, cliente) and cupon.usos.count() < cupon.usos_maximos and cupon.usos.filter(pedido__cliente=cliente).count() < cupon.limite_por_cliente:
            if dry_run:
                total += not NotificacionEnviada.objects.filter(clave_evento=f'cupon:{cupon.pk}:{cliente.pk}').exists()
                continue
            _, creada = crear_notificacion(tienda=cupon.tienda, cliente=cliente,
                titulo='Una promoción para ti', mensaje=f'Usa {cupon.codigo} en {cupon.tienda.nombre}. Consulta sus condiciones.',
                tipo='cupon', datos={'cupon_id': cupon.pk}, clave=f'cupon:{cupon.pk}:{cliente.pk}')
            total += creada
    return total
