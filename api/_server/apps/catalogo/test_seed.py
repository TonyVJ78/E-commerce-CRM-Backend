from unittest.mock import patch

from django.test import TestCase

import seed_demo

from .models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Usuario


class DemoSeederTests(TestCase):
    @patch('seed_demo.cloudinary_demo_image')
    @patch('seed_demo._cloudinary_uploader')
    def test_seed_is_idempotent(self, cloudinary_uploader, demo_image):
        cloudinary_uploader.return_value = object()
        demo_image.side_effect = lambda uploader, public_id, source: {
            'url': f'https://cloudinary.test/{public_id}.webp',
            'public_id': public_id,
        }

        seed_demo.main()
        counts_after_first = (
            Usuario.objects.count(),
            Tienda.objects.count(),
            Producto.objects.count(),
            Variante.objects.count(),
        )
        seed_demo.main()
        counts_after_second = (
            Usuario.objects.count(),
            Tienda.objects.count(),
            Producto.objects.count(),
            Variante.objects.count(),
        )

        self.assertEqual(counts_after_first, counts_after_second)
        self.assertEqual(Usuario.objects.filter(email='empresa2@kantu.bo').count(), 1)
        self.assertEqual(
            Producto.objects.filter(slug='polera-kantu').count(),
            1,
        )
        self.assertEqual(
            Variante.objects.filter(sku='POL-RO-M').count(),
            1,
        )
        self.assertEqual(
            Variante.objects.filter(producto__slug='chompa-de-alpaca', stock=0).count(),
            3,
        )
        self.assertEqual(
            Variante.objects.get(sku='MAN-ART-UNICA').stock_minimo,
            5,
        )
        self.assertEqual(demo_image.call_count, 10)
