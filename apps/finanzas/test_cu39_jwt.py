"""Solicitudes REST con login y JWT normales en la base independiente del runner.

Las claves aleatorias y los tokens existen solo durante cada prueba. No se
imprimen ni se escriben en la evidencia. No se utiliza force_authenticate.
"""
import secrets

from django.test import override_settings
from rest_framework.test import APITestCase
from apps.usuarios.models import Usuario, Rol
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante, Categoria


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'])
class SeguridadEmpresaJWTTests(APITestCase):
    observaciones = []

    def registrar(self, caso, metodo, ruta, respuesta, esperado):
        self.observaciones.append({'caso':caso,'metodo':metodo,'ruta':ruta,
                                    'http':respuesta.status_code,'esperado':esperado})
        self.assertEqual(respuesta.status_code, esperado)

    def login(self, usuario, clave):
        self.client.credentials()
        r = self.client.post('/api/auth/login/', {'email':usuario.email,'password':clave}, format='json')
        self.registrar('login_'+usuario.rol.nombre, 'POST', '/api/auth/login/', r, 200)
        self.assertEqual(r.data['usuario']['rol'], usuario.rol.nombre)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+r.data['access'])

    def setUp(self):
        self.observaciones = []
        empresa = Rol.objects.get(nombre='empresa')
        cliente = Rol.objects.get(nombre='cliente')
        self.clave_a, self.clave_b, self.clave_c = (secrets.token_urlsafe(32) for _ in range(3))
        self.a = Usuario.objects.create_user('jwt-a@example.test', self.clave_a, rol=empresa)
        self.b = Usuario.objects.create_user('jwt-b@example.test', self.clave_b, rol=empresa)
        self.c = Usuario.objects.create_user('jwt-cliente@example.test', self.clave_c, rol=cliente)
        self.ta = Tienda.objects.create(propietario=self.a, nombre='JWT Tienda A sintética', slug='jwt-a')
        self.tb = Tienda.objects.create(propietario=self.b, nombre='JWT Tienda B sintética', slug='jwt-b')
        self.pa = Producto.objects.create(tienda=self.ta, nombre='Producto A', slug='a')
        self.pb = Producto.objects.create(tienda=self.tb, nombre='Producto B', slug='b')
        self.va = Variante.objects.create(producto=self.pa, sku='JWT-A', precio=64, stock=10)
        self.vb = Variante.objects.create(producto=self.pb, sku='JWT-B', precio=80, stock=10)
        self.cb = Categoria.objects.create(tienda=self.tb, nombre='Categoría B')
        self.url_a = f'/api/tiendas/{self.ta.pk}/productos/{self.pa.pk}/'
        self.url_b = f'/api/tiendas/{self.tb.pk}/productos/{self.pb.pk}/'
        self.login(self.a, self.clave_a)

    def snapshot(self):
        return (list(Producto.objects.order_by('pk').values()), list(Variante.objects.order_by('pk').values()))

    def test_01_empresa_no_edita_producto_de_otra_tienda(self):
        antes = self.snapshot()
        self.registrar('propietario_lectura', 'GET', self.url_a, self.client.get(self.url_a), 200)
        self.registrar('otra_tienda_lectura', 'GET', self.url_b, self.client.get(self.url_b), 404)
        r = self.client.patch(self.url_b, {'precio':'0.01'}, format='json')
        self.registrar('otra_tienda_edicion', 'PATCH', self.url_b, r, 404)
        self.assertEqual(self.snapshot(), antes)

    def test_02_no_admite_variante_categoria_o_traslado_ajenos(self):
        antes = self.snapshot()
        for caso, datos in (
            ('variante_ajena', {'variante_id':self.vb.pk,'precio':'1.00'}),
            ('categoria_ajena', {'categoria_id':self.cb.pk}),
            ('traslado_tienda', {'tienda':self.tb.pk}),
        ):
            r = self.client.patch(self.url_a, datos, format='json')
            self.registrar(caso, 'PATCH', self.url_a, r, 400)
        self.assertEqual(self.snapshot(), antes)

    def test_03_cliente_anonimo_y_jwt_invalido_no_editan(self):
        antes = self.snapshot()
        self.login(self.c, self.clave_c)
        r = self.client.patch(self.url_a, {'precio':'1'}, format='json')
        self.registrar('cliente_sin_rol_empresa', 'PATCH', self.url_a, r, 403)
        self.client.credentials()
        r = self.client.patch(self.url_a, {'precio':'1'}, format='json')
        self.registrar('anonimo', 'PATCH', self.url_a, r, 401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer jwt_invalido_de_prueba')
        r = self.client.patch(self.url_a, {'precio':'1'}, format='json')
        self.registrar('jwt_invalido', 'PATCH', self.url_a, r, 401)
        self.assertEqual(self.snapshot(), antes)

    def test_04_otra_empresa_no_accede_a_variante_ni_stock_ajenos(self):
        antes = self.snapshot()
        self.login(self.b, self.clave_b)
        self.registrar('empresa_b_lee_su_producto', 'GET', self.url_b, self.client.get(self.url_b), 200)
        r = self.client.patch(self.url_a, {'variante_id':self.va.pk,'precio':'0.01'}, format='json')
        self.registrar('empresa_b_edita_variante_a', 'PATCH', self.url_a, r, 404)
        url = f'/api/tiendas/{self.ta.pk}/variantes/{self.va.pk}/stock/'
        r = self.client.post(url, {'delta':1,'reason':'Ensayo sintético denegado'}, format='json')
        self.registrar('empresa_b_modifica_stock_a', 'POST', url, r, 404)
        self.assertEqual(self.snapshot(), antes)
