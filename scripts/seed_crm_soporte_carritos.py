"""
Script de población para CU-26 (Soporte / Reclamos) y CU-27 (Carritos Abandonados).
Ejecutar con: python scripts/seed_crm_soporte_carritos.py
"""

import os
import sys
import django
from decimal import Decimal

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from apps.usuarios.models import Usuario, Rol
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import Pedido, Carrito, ItemCarrito
from apps.crm.models import (
    TicketSoporte,
    MensajeTicket,
    CampanaCarrito,
    RegistroRecuperacionCarrito,
)


def seed():
    print("[CRM SEED] Iniciando seeding de datos para CU-26 y CU-27...")

    # 1. Obtener o crear usuarios
    rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')
    
    carlos, _ = Usuario.objects.get_or_create(
        email='carlos.mendoza@kantu.bo',
        defaults={
            'username': 'carlos.mendoza',
            'first_name': 'Carlos',
            'last_name': 'Mendoza',
            'rol': rol_cliente,
            'is_active': True,
        }
    )
    if not carlos.check_password('password123'):
        carlos.set_password('password123')
        carlos.save()

    cliente1 = Usuario.objects.filter(email='cliente1@kantu.bo').first() or carlos
    cliente2 = Usuario.objects.filter(email='cliente2@kantu.bo').first() or carlos

    empresa1 = Usuario.objects.filter(email='empresa1@kantu.bo').first()
    empresa2 = Usuario.objects.filter(email='empresa2@kantu.bo').first()

    # 2. Tiendas
    tienda1 = Tienda.objects.filter(id=1).first() or Tienda.objects.filter(propietario=empresa2).first()
    tienda3 = Tienda.objects.filter(id=3).first() or Tienda.objects.filter(propietario=empresa1).first()

    if not tienda1 or not tienda3:
        print("[ERROR] No se encontraron Tienda 1 y Tienda 3 en la base de datos.")
        return

    print(f"Tienda 1: {tienda1.nombre} ({tienda1.propietario.email})")
    print(f"Tienda 3: {tienda3.nombre} ({tienda3.propietario.email})")

    # Obtener pedidos reales de estos clientes para asociar opcionalmente
    pedidos_c1 = list(Pedido.objects.filter(cliente=cliente1, tienda=tienda3))
    pedidos_c2 = list(Pedido.objects.filter(cliente=cliente2, tienda=tienda1))

    # 3. Tickets de Soporte (CU-26) - Al menos 6 tickets
    tickets_data = [
        {
            'tienda': tienda3,
            'cliente': cliente1,
            'pedido': pedidos_c1[0] if pedidos_c1 else None,
            'tipo': 'consulta',
            'prioridad': 'media',
            'estado': 'abierto',
            'asunto': 'Consulta sobre composicion de bufanda de alpaca',
            'descripcion': 'Buenas tardes, quisiera saber que porcentaje de fibra de alpaca pura tiene la bufanda andina artesanal.',
            'dias_atras': 1,
            'mensajes': [
                (cliente1, 'Buenas tardes, quisiera saber que porcentaje de fibra de alpaca pura tiene la bufanda andina artesanal.', 24),
            ]
        },
        {
            'tienda': tienda3,
            'cliente': cliente2,
            'pedido': pedidos_c1[0] if pedidos_c1 else None,
            'tipo': 'reclamo_producto',
            'prioridad': 'alta',
            'estado': 'en_proceso',
            'asunto': 'Defecto en costura de poncho tradicional',
            'descripcion': 'El poncho que recibi la semana pasada tiene un deshilachado visible en el dobladillo lateral.',
            'dias_atras': 3,
            'mensajes': [
                (cliente2, 'El poncho que recibi la semana pasada tiene un deshilachado visible en el dobladillo lateral.', 72),
                (tienda3.propietario, 'Estimado Pedro, lamentamos el inconveniente. Podrias enviarnos una fotografia para coordinar el cambio sin costo?', 48),
                (cliente2, 'Ya adjunte la imagen en el pedido. Espero su confirmacion del reemplazo.', 24),
            ]
        },
        {
            'tienda': tienda3,
            'cliente': carlos,
            'pedido': None,
            'tipo': 'demora_envio',
            'prioridad': 'urgente',
            'estado': 'resuelto',
            'asunto': 'Demora en envio a zona sur de La Paz',
            'descripcion': 'Mi orden debio llegar hace 48 horas segun la guia de transporte y no tengo actualizacion.',
            'dias_atras': 5,
            'mensajes': [
                (carlos, 'Mi orden debio llegar hace 48 horas segun la guia de transporte y no tengo actualizacion.', 120),
                (tienda3.propietario, 'Hola Carlos, verificamos con la empresa de mensajeria y hubo un retraso por lluvias. El paquete ya fue entregado.', 72),
                (carlos, 'Paquete recibido correctamente. Muchas gracias por la gestion.', 24),
            ]
        },
        {
            'tienda': tienda1,
            'cliente': cliente1,
            'pedido': None,
            'tipo': 'consulta',
            'prioridad': 'baja',
            'estado': 'abierto',
            'asunto': 'Disponibilidad de café yungueño en grano',
            'descripcion': 'Tienen previsto reponer stock del café tostado oscuro en presentacion de 1 kg esta semana?',
            'dias_atras': 2,
            'mensajes': [
                (cliente1, 'Tienen previsto reponer stock del café tostado oscuro en presentacion de 1 kg esta semana?', 48),
            ]
        },
        {
            'tienda': tienda1,
            'cliente': cliente2,
            'pedido': pedidos_c2[0] if pedidos_c2 else None,
            'tipo': 'devolucion',
            'prioridad': 'alta',
            'estado': 'en_proceso',
            'asunto': 'Solicitud de devolucion por producto incorrecto',
            'descripcion': 'Recibi miel de bosque en lugar del propoleo organico que solicite en mi pedido.',
            'dias_atras': 4,
            'mensajes': [
                (cliente2, 'Recibi miel de bosque en lugar del propoleo organico que solicite en mi pedido.', 96),
                (tienda1.propietario, 'Disculpas por la confusion en bodega. Estamos despachando el propoleo correcto hoy mismo con guia prioritaria.', 48),
            ]
        },
        {
            'tienda': tienda1,
            'cliente': carlos,
            'pedido': None,
            'tipo': 'reclamo_producto',
            'prioridad': 'media',
            'estado': 'resuelto',
            'asunto': 'Frasco de mermelada con precinto alterado',
            'descripcion': 'Uno de los frascos de mermelada de copoazú llego con la tapa floja.',
            'dias_atras': 7,
            'mensajes': [
                (carlos, 'Uno de los frascos de mermelada de copoazú llego con la tapa floja.', 168),
                (tienda1.propietario, 'Estimado Carlos, hemos emitido una nota de credito y reposicion inmediata para tu proxima compra.', 120),
                (carlos, 'De acuerdo, solucion aceptada. Gracias por la atencion rapida.', 72),
            ]
        },
    ]

    for item in tickets_data:
        ticket, created = TicketSoporte.objects.get_or_create(
            tienda=item['tienda'],
            cliente=item['cliente'],
            asunto=item['asunto'],
            defaults={
                'pedido': item['pedido'],
                'tipo': item['tipo'],
                'prioridad': item['prioridad'],
                'estado': item['estado'],
                'descripcion': item['descripcion'],
            }
        )
        if created:
            fecha_t = timezone.now() - timezone.timedelta(days=item['dias_atras'])
            TicketSoporte.objects.filter(id=ticket.id).update(fecha_creacion=fecha_t, fecha_actualizacion=fecha_t)
            
            for autor, texto, horas_atras in item['mensajes']:
                m = MensajeTicket.objects.create(
                    ticket=ticket,
                    autor=autor,
                    contenido=texto,
                )
                fecha_m = timezone.now() - timezone.timedelta(hours=horas_atras)
                MensajeTicket.objects.filter(id=m.id).update(fecha_envio=fecha_m)

    print(f"[CRM SEED] {len(tickets_data)} Tickets de soporte creados o verificados.")

    # 4. Configurar Campañas de Carrito Abandonado (CU-27)
    campana_t3, _ = CampanaCarrito.objects.get_or_create(
        tienda=tienda3,
        defaults={
            'activo': True,
            'horas_inactividad': 2,
            'asunto_email': f'Tus articulos artesanales te esperan en {tienda3.nombre}',
            'mensaje_email': (
                f'Hola. Dejaste productos seleccionados en tu carrito de {tienda3.nombre}. '
                f'Completa tu compra hoy y llevate un 10% de descuento con el cupon KANTU10.'
            ),
            'descuento_porcentaje': 10,
            'codigo_cupon': 'KANTU10',
        }
    )
    campana_t3.activo = True
    campana_t3.descuento_porcentaje = 10
    campana_t3.codigo_cupon = 'KANTU10'
    campana_t3.save()

    campana_t1, _ = CampanaCarrito.objects.get_or_create(
        tienda=tienda1,
        defaults={
            'activo': True,
            'horas_inactividad': 3,
            'asunto_email': f'Sabores bolivianos esperan por ti en {tienda1.nombre}',
            'mensaje_email': (
                f'Notamos que tienes productos en tu carrito. '
                f'Finaliza tu pedido antes de que se agoten nuestros lotes organicos frescos.'
            ),
            'descuento_porcentaje': 5,
            'codigo_cupon': 'SABORES5',
        }
    )
    campana_t1.activo = True
    campana_t1.save()

    print("[CRM SEED] Campañas de carrito abandonado configuradas para Tienda 1 y Tienda 3.")

    # 5. Generar Carritos Abandonados con Productos Reales
    # Obtener variantes de Tienda 3
    variantes_t3 = list(Variante.objects.filter(producto__tienda=tienda3, producto__activo=True))
    variantes_t1 = list(Variante.objects.filter(producto__tienda=tienda1, producto__activo=True))

    if variantes_t3:
        carritos_t3_seed = [
            (cliente1, 4, [variantes_t3[0]]),
            (cliente2, 12, variantes_t3[:2]),
            (carlos, 36, [variantes_t3[-1]]),
        ]

        for cli, horas, vars_list in carritos_t3_seed:
            c, _ = Carrito.objects.get_or_create(cliente=cli, tienda=tienda3)
            c.items.all().delete()
            for v in vars_list:
                ItemCarrito.objects.create(tienda=tienda3, carrito=c, variante=v, cantidad=1)
            fecha_c = timezone.now() - timezone.timedelta(hours=horas)
            Carrito.objects.filter(id=c.id).update(fecha_creacion=fecha_c)

            # Notificacion para el de 12 horas
            if horas == 12:
                reg, _ = RegistroRecuperacionCarrito.objects.get_or_create(
                    campana=campana_t3,
                    carrito=c,
                    cliente=cli,
                    defaults={'recuperado': False}
                )
            elif horas == 36:
                reg, _ = RegistroRecuperacionCarrito.objects.get_or_create(
                    campana=campana_t3,
                    carrito=c,
                    cliente=cli,
                    defaults={'recuperado': True}
                )

    if variantes_t1:
        carritos_t1_seed = [
            (carlos, 6, [variantes_t1[0]]),
            (cliente2, 28, variantes_t1[:2]),
        ]

        for cli, horas, vars_list in carritos_t1_seed:
            c, _ = Carrito.objects.get_or_create(cliente=cli, tienda=tienda1)
            c.items.all().delete()
            for v in vars_list:
                ItemCarrito.objects.create(tienda=tienda1, carrito=c, variante=v, cantidad=2)
            fecha_c = timezone.now() - timezone.timedelta(hours=horas)
            Carrito.objects.filter(id=c.id).update(fecha_creacion=fecha_c)

            if horas == 28:
                RegistroRecuperacionCarrito.objects.get_or_create(
                    campana=campana_t1,
                    carrito=c,
                    cliente=cli,
                    defaults={'recuperado': False}
                )

    print("[CRM SEED] Carritos abandonados e historico de recuperacion creados exitosamente.")
    print("[CRM SEED] Seeding finalizado con exito.")


if __name__ == '__main__':
    seed()
