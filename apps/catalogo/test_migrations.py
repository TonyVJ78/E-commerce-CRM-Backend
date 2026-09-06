from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CatalogDataMigrationTests(TransactionTestCase):
    """Verifica la conversion desde el esquema transitorio de CU08."""

    migrate_from = ('catalogo', '0003_alter_producto_actualizado_alter_producto_creado')
    migrate_to = ('catalogo', '0004_migrar_datos_cu08')

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        self._create_legacy_data()
        self.executor.migrate([self.migrate_to])
        self.new_apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())

    def _create_legacy_data(self):
        Tienda = self.old_apps.get_model('tiendas', 'Tienda')
        Categoria = self.old_apps.get_model('catalogo', 'Categoria')
        Producto = self.old_apps.get_model('catalogo', 'Producto')
        Variante = self.old_apps.get_model('catalogo', 'Variante')
        Inventario = self.old_apps.get_model('catalogo', 'Inventario')
        Atributo = self.old_apps.get_model('catalogo', 'Atributo')
        VarianteAtributo = self.old_apps.get_model('catalogo', 'VarianteAtributo')
        ImagenProducto = self.old_apps.get_model('catalogo', 'ImagenProducto')
        Etiqueta = self.old_apps.get_model('catalogo', 'Etiqueta')
        ProductoEtiqueta = self.old_apps.get_model('catalogo', 'ProductoEtiqueta')
        Carrito = self.old_apps.get_model('pedidos', 'Carrito')
        ItemCarrito = self.old_apps.get_model('pedidos', 'ItemCarrito')
        Pedido = self.old_apps.get_model('pedidos', 'Pedido')
        ItemPedido = self.old_apps.get_model('pedidos', 'ItemPedido')

        Usuario = self.old_apps.get_model('usuarios', 'Usuario')
        Rol = self.old_apps.get_model('usuarios', 'Rol')
        rol = Rol.objects.create(nombre='empresa')
        owner = Usuario.objects.create_user(
            email='migration@test.local',
            password='Password123!',
            rol=rol,
        )
        store = Tienda.objects.create(
            propietario=owner,
            nombre='Tienda migracion',
            slug='tienda-migracion',
        )
        category = Categoria.objects.create(tienda=store, nombre='Ropa')
        first = Producto.objects.create(
            tienda=store,
            categoria=category,
            nombre='Polera Migrada',
            descripcion='Descripcion antigua',
            precio_base=Decimal('100.00'),
            sku='PROD-MIG',
        )
        second = Producto.objects.create(
            tienda=store,
            categoria=category,
            nombre='Polera Migrada',
            descripcion='Sin variantes',
            precio_base=Decimal('80.00'),
            sku='',
        )
        variant = Variante.objects.create(
            tienda=store,
            producto=first,
            nombre='Rojo',
            precio_adicional=Decimal('10.00'),
            sku='',
        )
        Inventario.objects.create(variante=variant, tienda=store, stock=3, umbral_minimo=2)
        Inventario.objects.create(variante=variant, tienda=store, stock=4, umbral_minimo=5)
        attribute = Atributo.objects.create(tienda=store, nombre='Color')
        VarianteAtributo.objects.create(
            tienda=store,
            variante=variant,
            atributo=attribute,
            valor='Rojo',
        )
        image = ImagenProducto.objects.create(
            tienda=store,
            producto=first,
            url='https://legacy.example/producto.jpg',
            orden=1,
        )
        tag = Etiqueta.objects.create(tienda=store, nombre='artesanal')
        ProductoEtiqueta.objects.create(tienda=store, producto=first, etiqueta=tag)
        cart = Carrito.objects.create(cliente=owner, tienda=store)
        order = Pedido.objects.create(
            cliente=owner,
            tienda=store,
            subtotal=Decimal('110.00'),
            total=Decimal('110.00'),
        )
        cart_item = ItemCarrito.objects.create(
            tienda=store,
            carrito=cart,
            variante=variant,
            cantidad=1,
        )
        order_item = ItemPedido.objects.create(
            tienda=store,
            pedido=order,
            variante=variant,
            cantidad=1,
            precio_unitario=Decimal('110.00'),
        )
        self.first_id = first.id
        self.second_id = second.id
        self.variant_id = variant.id
        self.image_url = image.url
        self.cart_item_id = cart_item.id
        self.order_item_id = order_item.id

    def test_products_variants_and_auxiliary_data_are_transformed(self):
        Producto = self.new_apps.get_model('catalogo', 'Producto')
        Variante = self.new_apps.get_model('catalogo', 'Variante')
        ItemCarrito = self.new_apps.get_model('pedidos', 'ItemCarrito')
        ItemPedido = self.new_apps.get_model('pedidos', 'ItemPedido')

        first = Producto.objects.get(pk=self.first_id)
        second = Producto.objects.get(pk=self.second_id)
        variant = Variante.objects.get(pk=self.variant_id)
        generated_variant = Variante.objects.get(producto_id=self.second_id)

        self.assertEqual(first.slug, 'polera-migrada')
        self.assertEqual(second.slug, 'polera-migrada-2')
        self.assertEqual(first.etiquetas, ['artesanal'])
        self.assertEqual(first.imagenes, [{'url': self.image_url, 'public_id': ''}])
        self.assertEqual(variant.precio, Decimal('110.00'))
        self.assertEqual(variant.stock, 7)
        self.assertEqual(variant.stock_minimo, 5)
        self.assertEqual(variant.sku, 'PROD-MIG')
        self.assertEqual(variant.atributos, {'color': 'Rojo'})
        self.assertEqual(generated_variant.nombre, 'Unica')
        self.assertEqual(generated_variant.sku, 'PROD-2')
        self.assertEqual(generated_variant.precio, Decimal('80.00'))
        self.assertEqual(
            ItemCarrito.objects.get(pk=self.cart_item_id).variante_id,
            self.variant_id,
        )
        self.assertEqual(
            ItemPedido.objects.get(pk=self.order_item_id).variante_id,
            self.variant_id,
        )
