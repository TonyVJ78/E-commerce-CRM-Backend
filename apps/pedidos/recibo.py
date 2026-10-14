"""CU-33 — Generación del recibo (factura en PDF) y envío por correo.

Al confirmarse una compra, el checkout llama a `enviar_recibos()`: arma un PDF
por pedido (uno por tienda) y los manda adjuntos al correo del cliente por el
SMTP configurado en el `.env` (Gmail en el entorno del equipo). El PDF también
se descarga desde `GET /api/pedidos/mis-pedidos/<id>/recibo/`.

El documento es un comprobante de compra, no una factura fiscal del SIN: no
lleva NIT, código de autorización ni código de control.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import escape
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from . import estados
from .models import Pedido

logger = logging.getLogger(__name__)

ROJO = (200, 16, 46)        # --primary #C8102E
AMARILLO = (244, 208, 63)   # --accent  #F4D03F
GRIS_TEXTO = (75, 85, 99)
GRIS_LINEA = (229, 231, 235)
GRIS_FONDO = (249, 250, 251)

ETIQUETA_ESTADO_PAGO = {
    'pagado': 'Pagado',
    'pendiente': 'Pendiente (contra entrega)',
    'reembolsado': 'Reembolsado',
}


def numero_recibo(pedido):
    return f'{pedido.id:08d}'


def nombre_archivo(pedido):
    return f'factura-kantu-{numero_recibo(pedido)}.pdf'


def pedidos_para_recibo(pedido_ids, cliente):
    """Pedidos del cliente con todo lo que el PDF necesita, en una sola consulta por relación."""
    return list(
        Pedido.objects.filter(pk__in=pedido_ids, cliente=cliente)
        .select_related('tienda', 'cliente')
        .prefetch_related('items__variante__producto', 'pagos__metodo_pago', 'tienda__direcciones')
        .order_by('id')
    )


# ---------------------------------------------------------------------------
# Importe en letras ("Son: ciento nueve 90/100 Bolivianos"), como en las
# facturas bolivianas.
# ---------------------------------------------------------------------------

_UNIDADES = [
    '', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve',
    'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete',
    'dieciocho', 'diecinueve', 'veinte', 'veintiuno', 'veintidós', 'veintitrés',
    'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho', 'veintinueve',
]
_DECENAS = ['', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
_CENTENAS = [
    '', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
    'seiscientos', 'setecientos', 'ochocientos', 'novecientos',
]


def _menor_que_mil(n):
    if n == 100:
        return 'cien'
    centenas, resto = divmod(n, 100)
    partes = [_CENTENAS[centenas]] if centenas else []
    if resto < 30:
        if resto:
            partes.append(_UNIDADES[resto])
    else:
        decenas, unidades = divmod(resto, 10)
        partes.append(_DECENAS[decenas] + (f' y {_UNIDADES[unidades]}' if unidades else ''))
    return ' '.join(partes)


def entero_en_letras(n):
    if n == 0:
        return 'cero'
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append('un millón' if millones == 1 else f'{_apocope(_menor_que_mil(millones))} millones')
    if miles:
        partes.append('mil' if miles == 1 else f'{_apocope(_menor_que_mil(miles))} mil')
    if unidades:
        partes.append(_menor_que_mil(unidades))
    return ' '.join(partes)


def _apocope(texto):
    # Delante de "mil"/"millones", "uno" se apocopa: "veintiún mil", "treinta y un mil".
    if texto.endswith('veintiuno'):
        return texto[:-len('veintiuno')] + 'veintiún'
    if texto.endswith('uno'):
        return texto[:-1]
    return texto


def monto_en_letras(monto):
    monto = Decimal(monto).quantize(Decimal('0.01'))
    entero = int(monto)
    centavos = int((monto - entero) * 100)
    return f'{entero_en_letras(entero).capitalize()} {centavos:02d}/100 Bolivianos'


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_TIPOGRAFICOS = str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-', '…': '...'})


def _t(texto):
    """Las fuentes estándar de PDF solo cubren latin-1: la puntuación tipográfica
    se pasa a su equivalente simple y el resto (emojis) se omite en vez de
    hacer fallar el recibo."""
    return str(texto or '').translate(_TIPOGRAFICOS).encode('latin-1', 'ignore').decode('latin-1')


def _bs(valor):
    return f'Bs {Decimal(valor):.2f}'


def _recortar(pdf, texto, ancho):
    texto = _t(texto)
    if pdf.get_string_width(texto) <= ancho:
        return texto
    while texto and pdf.get_string_width(texto + '...') > ancho:
        texto = texto[:-1]
    return texto + '...'


class _ReciboPDF(FPDF):
    def footer(self):
        self.set_y(-18)
        self.set_draw_color(*GRIS_LINEA)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_font('Helvetica', '', 7.5)
        self.set_text_color(*GRIS_TEXTO)
        self.multi_cell(
            0, 3.6,
            _t('Comprobante de compra emitido por Kantu Market. No válido para crédito fiscal. '
               f'Página {self.page_no()}/{{nb}}'),
            align='C',
        )


def _pagina_pedido(pdf, pedido):
    pdf.add_page()
    ancho = pdf.w - pdf.l_margin - pdf.r_margin
    tienda = pedido.tienda
    cliente = pedido.cliente
    pago = min(pedido.pagos.all(), key=lambda p: p.id, default=None)
    direccion = min(tienda.direcciones.all(), key=lambda d: d.id, default=None)
    fecha = timezone.localtime(pedido.fecha) if pedido.fecha else timezone.localtime()

    # Banda superior con la marca
    pdf.set_fill_color(*ROJO)
    pdf.rect(0, 0, pdf.w, 30, style='F')
    pdf.set_fill_color(*AMARILLO)
    pdf.rect(0, 30, pdf.w, 1.6, style='F')
    pdf.set_xy(pdf.l_margin, 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 20)
    pdf.cell(ancho / 2, 8, 'KANTU MARKET')
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(ancho / 2, 8, 'FACTURA', align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(ancho / 2, 5, _t('Marketplace de empresas bolivianas'))
    pdf.cell(ancho / 2, 5, _t(f'Recibo de compra N° {numero_recibo(pedido)}'), align='R')

    # Datos del vendedor y del cliente, en dos columnas
    pdf.set_y(40)
    col = ancho / 2 - 4
    y0 = pdf.get_y()

    def bloque(x, titulo, lineas):
        pdf.set_xy(x, y0)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*ROJO)
        pdf.cell(col, 5, titulo, new_x=XPos.LEFT, new_y=YPos.NEXT)
        for i, linea in enumerate(lineas):
            pdf.set_font('Helvetica', 'B' if i == 0 else '', 10 if i == 0 else 9)
            pdf.set_text_color(*((17, 24, 39) if i == 0 else GRIS_TEXTO))
            pdf.cell(col, 5, _recortar(pdf, linea, col), new_x=XPos.LEFT, new_y=YPos.NEXT)
        return pdf.get_y()

    vendedor = [tienda.nombre]
    if direccion:
        vendedor.append(f'{direccion.direccion}, {direccion.ciudad}')
        if direccion.telefono:
            vendedor.append(f'Tel. {direccion.telefono}')
    nombre_cliente = cliente.get_full_name().strip() or cliente.email
    datos_cliente = [nombre_cliente, cliente.email, f'Fecha: {fecha:%d/%m/%Y %H:%M}']

    fin_izq = bloque(pdf.l_margin, 'VENDIDO POR', vendedor)
    fin_der = bloque(pdf.l_margin + ancho / 2 + 4, 'FACTURADO A', datos_cliente)
    pdf.set_y(max(fin_izq, fin_der) + 8)

    # Detalle
    columnas = [('Cant.', 16, 'C'), ('Descripción', ancho - 16 - 34 - 34, 'L'),
                ('P. unitario', 34, 'R'), ('Subtotal', 34, 'R')]
    pdf.set_fill_color(*ROJO)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 9)
    for titulo, w, alineacion in columnas:
        pdf.cell(w, 8, _t(titulo), align=alineacion, fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(17, 24, 39)
    for i, item in enumerate(pedido.items.all()):
        producto = item.variante.producto.nombre if item.variante_id else 'Producto'
        variante = item.variante.nombre if item.variante_id else ''
        descripcion = producto if not variante or variante.lower() in ('unica', 'única') else f'{producto} - {variante}'
        fila = [str(item.cantidad), descripcion, _bs(item.precio_unitario), _bs(item.cantidad * item.precio_unitario)]
        pdf.set_fill_color(*(GRIS_FONDO if i % 2 else (255, 255, 255)))
        for (_, w, alineacion), valor in zip(columnas, fila):
            pdf.cell(w, 7.5, _recortar(pdf, valor, w - 2), align=alineacion, fill=True)
        pdf.ln()

    pdf.set_draw_color(*GRIS_LINEA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # Totales
    etiqueta_w, valor_w = 40, 34
    x_totales = pdf.w - pdf.r_margin - etiqueta_w - valor_w
    pdf.set_font('Helvetica', '', 9.5)
    pdf.set_text_color(*GRIS_TEXTO)
    pdf.set_x(x_totales)
    pdf.cell(etiqueta_w, 6, 'Subtotal', align='R')
    pdf.cell(valor_w, 6, _bs(pedido.subtotal), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(x_totales)
    pdf.set_fill_color(*ROJO)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(etiqueta_w, 9, 'TOTAL', align='R', fill=True)
    pdf.cell(valor_w, 9, _bs(pedido.total) + ' ', align='R', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_text_color(17, 24, 39)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(10, 5, 'Son:')
    pdf.set_font('Helvetica', '', 9)
    pdf.multi_cell(0, 5, _t(monto_en_letras(pedido.total)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Pago y estado
    pdf.ln(5)
    pdf.set_fill_color(*GRIS_FONDO)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(*ROJO)
    pdf.cell(0, 6, ' DATOS DEL PAGO', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*GRIS_TEXTO)
    pdf.set_font('Helvetica', '', 9)
    filas_pago = [
        ('Método de pago', pago.metodo_pago.nombre if pago else 'No registrado'),
        ('Estado del pago', ETIQUETA_ESTADO_PAGO.get(pago.estado, pago.estado.capitalize()) if pago else '-'),
        ('Estado del pedido', estados.etiqueta(pedido.estado_actual)),
    ]
    if pago and pago.referencia_transaccion:
        filas_pago.append(('Referencia', pago.referencia_transaccion))
    for etiqueta, valor in filas_pago:
        pdf.cell(40, 5.5, _t(f' {etiqueta}:'), fill=True)
        pdf.cell(0, 5.5, _recortar(pdf, valor, ancho - 42), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(8)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(*GRIS_TEXTO)
    pdf.multi_cell(0, 5, _t('¡Gracias por comprar en Kantu Market! Puedes seguir el estado de tu pedido '
                            'en la sección "Mis pedidos" de la plataforma.'), align='C')


def generar_recibo_pdf(pedido):
    """Devuelve los bytes del PDF de un pedido (con sus relaciones ya cargadas
    vía `pedidos_para_recibo` para no disparar consultas por ítem)."""
    pdf = _ReciboPDF(format='A4')
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=24)
    pdf.set_title(_t(f'Factura Kantu Market N° {numero_recibo(pedido)}'))
    pdf.set_author('Kantu Market')
    _pagina_pedido(pdf, pedido)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Correo
# ---------------------------------------------------------------------------

def _cuerpo_html(cliente, pedidos):
    filas = ''.join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #E5E7EB">#{numero_recibo(p)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E5E7EB">{escape(p.tienda.nombre)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E5E7EB;text-align:right">{_bs(p.total)}</td></tr>'
        for p in pedidos
    )
    total = sum((p.total for p in pedidos), Decimal('0'))
    nombre = escape(cliente.first_name or cliente.get_full_name() or cliente.email)
    url_pedidos = f"{settings.FRONTEND_URL.rstrip('/')}/pedidos"
    return f"""\
<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;color:#111827">
  <div style="background:#C8102E;color:#fff;padding:20px 24px;border-bottom:4px solid #F4D03F">
    <h1 style="margin:0;font-size:20px">Kantu Market</h1>
    <p style="margin:4px 0 0;font-size:13px">Gracias por tu compra</p>
  </div>
  <div style="padding:24px">
    <p>Hola {nombre},</p>
    <p>Tu compra se registró correctamente. Adjuntamos la factura en PDF de cada pedido.</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin:16px 0">
      <thead><tr style="background:#F9FAFB;text-align:left">
        <th style="padding:8px 12px">Pedido</th><th style="padding:8px 12px">Tienda</th>
        <th style="padding:8px 12px;text-align:right">Total</th></tr></thead>
      <tbody>{filas}</tbody>
      <tfoot><tr><td colspan="2" style="padding:10px 12px;font-weight:700">Total pagado</td>
        <td style="padding:10px 12px;font-weight:700;text-align:right;color:#C8102E">{_bs(total)}</td></tr></tfoot>
    </table>
    <p><a href="{url_pedidos}" style="display:inline-block;background:#C8102E;color:#fff;padding:10px 18px;
      border-radius:8px;text-decoration:none;font-weight:600">Ver mis pedidos</a></p>
    <p style="font-size:12px;color:#6B7280;margin-top:24px">Este correo se generó automáticamente;
      no respondas a este mensaje.</p>
  </div>
</div>"""


def _cuerpo_texto(cliente, pedidos):
    lineas = [f'Hola {cliente.first_name or cliente.email},', '',
              'Tu compra en Kantu Market se registró correctamente. Adjuntamos la factura de cada pedido:', '']
    lineas += [f'  - Pedido #{numero_recibo(p)} · {p.tienda.nombre} · {_bs(p.total)}' for p in pedidos]
    lineas += ['', f"Sigue tus pedidos en {settings.FRONTEND_URL.rstrip('/')}/pedidos", '', 'Kantu Market']
    return '\n'.join(lineas)


def enviar_recibos(cliente, pedido_ids):
    """Envía al cliente un correo con la factura PDF de cada pedido.

    Devuelve True si el correo salió. Nunca lanza: un fallo de SMTP no puede
    deshacer una compra ya cobrada, así que solo se registra en el log y el
    cliente puede reenviarlo desde "Mis pedidos".
    """
    if not cliente.email:
        return False
    try:
        pedidos = pedidos_para_recibo(pedido_ids, cliente)
        if not pedidos:
            return False
        if len(pedidos) == 1:
            asunto = f'Tu factura de Kantu Market - Pedido #{numero_recibo(pedidos[0])}'
        else:
            asunto = f'Tus facturas de Kantu Market - {len(pedidos)} pedidos'
        correo = EmailMultiAlternatives(
            subject=asunto,
            body=_cuerpo_texto(cliente, pedidos),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[cliente.email],
        )
        correo.attach_alternative(_cuerpo_html(cliente, pedidos), 'text/html')
        for pedido in pedidos:
            correo.attach(nombre_archivo(pedido), generar_recibo_pdf(pedido), 'application/pdf')
        correo.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('No se pudo enviar el recibo de los pedidos %s a %s', pedido_ids, cliente.email)
        return False
