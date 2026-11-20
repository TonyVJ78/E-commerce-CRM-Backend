"""Entrena los modelos de una tienda y los guarda en `ModeloML`."""

from ..models import ModeloML
from . import abandono, compras_conjuntas, datos as carga, pronostico

MODULOS = [pronostico, abandono, compras_conjuntas]


def entrenar_tienda(tienda, hasta=None) -> list[dict]:
    """Entrena los tres modelos. Devuelve los que no se pudieron entrenar con su motivo."""
    datos = carga.cargar(tienda, hasta)
    omitidos = []
    for modulo in MODULOS:
        try:
            ajuste = modulo.entrenar(datos)
        except carga.DatosInsuficientes as motivo:
            ModeloML.objects.filter(tienda=tienda, tipo=modulo.TIPO).delete()
            omitidos.append({'tipo': modulo.TIPO, 'titulo': modulo.TITULO, 'motivo': str(motivo)})
            continue
        ModeloML.objects.update_or_create(
            tienda=tienda,
            tipo=modulo.TIPO,
            defaults={
                'algoritmo': ajuste['algoritmo'],
                'parametros': ajuste['parametros'],
                'metricas': ajuste['metricas'],
                'resultados': ajuste['resultados'],
                'filas_entrenamiento': ajuste['filas_entrenamiento'],
            },
        )
    return omitidos
