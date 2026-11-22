"""Operaciones puras: importes Decimal, sin ORM ni consultas de cotizaciones."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


def convertir_importe(monto, *, bob_por_origen=Decimal('1'), bob_por_destino):
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            monto, origen, destino = map(lambda v: Decimal(str(v)), (monto, bob_por_origen, bob_por_destino))
            if not all(v.is_finite() for v in (monto, origen, destino)) or monto < 0 or origen <= 0 or destino <= 0:
                raise ValueError('Importe o tasa no válidos.')
            convertido = (monto * origen / destino).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if convertido > Decimal('9999999999.99'):
                raise ValueError('Equivalencia fuera de rango.')
            return convertido
    except (InvalidOperation, ArithmeticError, TypeError) as exc:
        raise ValueError('No se puede representar la equivalencia.') from exc
