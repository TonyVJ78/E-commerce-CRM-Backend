"""Pruebas de CU-33 (factura en PDF enviada por correo tras la compra).

El runner de Django usa el backend de correo en memoria (`mail.outbox`), así
que no sale ningún correo real. Requieren PostgreSQL, como el resto del checkout.
"""

from decimal import Decimal
from smtplib import SMTPException
from unittest import mock

from django.core import mail
from django.test import SimpleTestCase

from . import recibo
from .models import Pedido
from .test_checkout_pedidos import BaseCompra


class ReciboCheckoutTests(BaseCompra):
    def test_la_compra_envia_la_factura_pdf_al_correo_del_cliente(self):
        self.llenar_carrito(cantidad=2)

        r = self.comprar(metodo_pago='efectivo')

        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['recibo_enviado'])
        self.assertEqual(r.data['recibo_email'], self.cliente.email)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.cliente.email])
        pedido = Pedido.objects.get(pk=r.data['pedidos'][0])
        self.assertIn(recibo.numero_recibo(pedido), correo.subject)
        nombre, contenido, tipo = correo.attachments[0]
        self.assertEqual(nombre, recibo.nombre_archivo(pedido))
        self.assertEqual(tipo, 'application/pdf')
        self.assertTrue(contenido.startswith(b'%PDF'))

    def test_si_falla_el_correo_la_compra_igual_se_registra(self):
        self.llenar_carrito()

        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=SMTPException('caído')):
            r = self.comprar(metodo_pago='efectivo')

        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.data['recibo_enviado'])
        self.assertTrue(Pedido.objects.filter(cliente=self.cliente).exists())
        self.assertEqual(self.stock(), 8)


class ReciboPedidoTests(BaseCompra):
    def setUp(self):
        super().setUp()
        self.llenar_carrito(cantidad=1)
        self.pedido_id = self.comprar(metodo_pago='efectivo').data['pedidos'][0]
        mail.outbox.clear()

    def test_el_cliente_descarga_la_factura_en_pdf(self):
        r = self.client.get(f'/api/pedidos/mis-pedidos/{self.pedido_id}/recibo/')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_otro_cliente_no_puede_ver_ni_reenviar_la_factura(self):
        self.client.force_authenticate(self.otro_cliente)

        descarga = self.client.get(f'/api/pedidos/mis-pedidos/{self.pedido_id}/recibo/')
        reenvio = self.client.post(f'/api/pedidos/mis-pedidos/{self.pedido_id}/recibo/enviar/')

        self.assertEqual(descarga.status_code, 404)
        self.assertEqual(reenvio.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_reenviar_la_factura(self):
        r = self.client.post(f'/api/pedidos/mis-pedidos/{self.pedido_id}/recibo/enviar/')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.cliente.email])

    def test_reenvio_fallido_devuelve_503(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=SMTPException('caído')):
            r = self.client.post(f'/api/pedidos/mis-pedidos/{self.pedido_id}/recibo/enviar/')

        self.assertEqual(r.status_code, 503)


class MontoEnLetrasTests(SimpleTestCase):
    def test_importes(self):
        casos = {
            Decimal('0.50'): 'Cero 50/100 Bolivianos',
            Decimal('109.90'): 'Ciento nueve 90/100 Bolivianos',
            Decimal('1219.80'): 'Mil doscientos diecinueve 80/100 Bolivianos',
            Decimal('21000'): 'Veintiún mil 00/100 Bolivianos',
            Decimal('31100.05'): 'Treinta y un mil cien 05/100 Bolivianos',
            Decimal('2500000'): 'Dos millones quinientos mil 00/100 Bolivianos',
        }
        for monto, esperado in casos.items():
            with self.subTest(monto=monto):
                self.assertEqual(recibo.monto_en_letras(monto), esperado)
