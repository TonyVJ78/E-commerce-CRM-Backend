"""Servicios externos usados por la identidad de marca de una tienda."""

from apps.catalogo.services import CloudinaryUploadError, _cloudinary_uploader


def upload_store_logo(image, tienda_id):
    """Sube un logo ya validado a una carpeta aislada por tienda."""
    uploader = _cloudinary_uploader()
    folder = f'kantu/tiendas/{tienda_id}/logo'

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
            'No se pudo subir el logotipo. Intenta nuevamente.'
        ) from exc

    url = result.get('secure_url', '')
    if not url:
        raise CloudinaryUploadError(
            'El proveedor de imágenes no devolvió una URL para el logotipo.'
        )

    return {
        'url': url,
        'public_id': result.get('public_id', ''),
    }


def delete_uploaded_logo(public_id):
    """Compensa una subida cuando el guardado posterior de la tienda falla."""
    if not public_id:
        return
    try:
        _cloudinary_uploader().destroy(
            public_id,
            resource_type='image',
            invalidate=True,
        )
    except Exception:
        # No se oculta el error original de base de datos/validación.
        return
