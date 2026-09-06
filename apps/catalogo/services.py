from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from .models import Producto, Variante


ALLOWED_IMAGE_TYPES = {
    'image/jpeg': b'jpeg',
    'image/png': b'png',
    'image/webp': b'webp',
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


class CloudinaryConfigurationError(RuntimeError):
    """Indica que Cloudinary no tiene todas las variables requeridas."""


class CloudinaryUploadError(RuntimeError):
    """Indica que Cloudinary rechazo o no pudo completar una operacion."""


def validate_product_image(image):
    if image is None:
        raise ValidationError('Debe proporcionar una imagen.')

    if getattr(image, 'size', 0) > MAX_IMAGE_SIZE:
        raise ValidationError('La imagen no puede superar los 5 MB.')

    content_type = getattr(image, 'content_type', '')
    expected_signature = ALLOWED_IMAGE_TYPES.get(content_type)
    if expected_signature is None:
        raise ValidationError('La imagen debe ser JPEG, PNG o WebP.')

    position = image.tell() if hasattr(image, 'tell') else 0
    header = image.read(12)
    if hasattr(image, 'seek'):
        image.seek(position)

    valid_signature = (
        expected_signature == b'jpeg' and header.startswith(b'\xff\xd8\xff')
    ) or (
        expected_signature == b'png' and header.startswith(b'\x89PNG\r\n\x1a\n')
    ) or (
        expected_signature == b'webp'
        and header.startswith(b'RIFF')
        and header[8:12] == b'WEBP'
    )
    if not valid_signature:
        raise ValidationError('El contenido de la imagen no coincide con su tipo.')


def _cloudinary_uploader():
    missing = [
        name for name, value in (
            ('CLOUDINARY_CLOUD_NAME', settings.CLOUDINARY_CLOUD_NAME),
            ('CLOUDINARY_API_KEY', settings.CLOUDINARY_API_KEY),
            ('CLOUDINARY_API_SECRET', settings.CLOUDINARY_API_SECRET),
        )
        if not value
    ]
    if missing:
        raise CloudinaryConfigurationError(
            'Cloudinary no esta configurado. Faltan: ' + ', '.join(missing) + '.'
        )

    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError as exc:
        raise CloudinaryConfigurationError(
            'El SDK de Cloudinary no esta instalado en el backend.'
        ) from exc

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    return cloudinary.uploader


def upload_product_image(image, tienda_id):
    """Valida y sube una imagen de producto, devolviendo solo datos publicos."""
    validate_product_image(image)
    uploader = _cloudinary_uploader()
    folder = f'kantu/tiendas/{tienda_id}/productos'

    try:
        result = uploader.upload(
            image,
            folder=folder,
            resource_type='image',
            use_filename=False,
            unique_filename=True,
            overwrite=False,
        )
    except Exception as exc:
        raise CloudinaryUploadError(
            'No se pudo subir la imagen a Cloudinary.'
        ) from exc

    return {
        'url': result.get('secure_url', ''),
        'public_id': result.get('public_id', ''),
    }


def delete_product_image(public_id):
    """Elimina una imagen subida previamente; un public_id vacio no hace nada."""
    if not public_id:
        return None

    uploader = _cloudinary_uploader()
    try:
        return uploader.destroy(
            public_id,
            resource_type='image',
            invalidate=True,
        )
    except Exception as exc:
        raise CloudinaryUploadError(
            'No se pudo eliminar la imagen de Cloudinary.'
        ) from exc


def _unique_product_slug(tienda, nombre):
    base_slug = slugify(nombre) or 'producto'
    slug = base_slug[:180]
    suffix = 2
    while Producto.objects.filter(tienda=tienda, slug=slug).exists():
        ending = f'-{suffix}'
        slug = f'{base_slug[:180 - len(ending)]}{ending}'
        suffix += 1
    return slug


def create_product_with_images(*, tienda, validated_data):
    """Sube imágenes y crea producto/variantes dentro de una transacción."""
    image_files = validated_data.pop('imagenes')
    uploaded_images = []

    try:
        for image in image_files:
            uploaded_images.append(upload_product_image(image, tienda.id))

        with transaction.atomic():
            producto = Producto.objects.create(
                tienda=tienda,
                categoria_id=validated_data.get('categoria_id'),
                nombre=validated_data['nombre'],
                slug=_unique_product_slug(tienda, validated_data['nombre']),
                descripcion=validated_data['descripcion'],
                etiquetas=validated_data.get('etiquetas', []),
                imagenes=uploaded_images,
                activo=validated_data.get('activo', True),
            )

            Variante.objects.bulk_create([
                Variante(
                    producto=producto,
                    nombre=variante.get('nombre') or 'Unica',
                    sku=variante['sku'],
                    precio=variante['precio'],
                    precio_oferta=variante.get('precio_oferta'),
                    stock=variante['stock'],
                    stock_minimo=variante['stock_minimo'],
                    atributos=variante.get('atributos', {}),
                    activa=variante.get('activa', True),
                )
                for variante in validated_data['variantes']
            ])
    except Exception:
        for image in uploaded_images:
            try:
                delete_product_image(image.get('public_id'))
            except Exception:
                pass
        raise

    return producto
