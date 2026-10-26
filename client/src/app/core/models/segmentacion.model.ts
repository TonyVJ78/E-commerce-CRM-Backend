export type TipoSegmento = 'ALTO_VALOR' | 'FRECUENTE' | 'INACTIVO' | 'NUEVO';

export interface ClienteSegmentado {
  id: number;
  cliente: {
    id: number;
    email: string;
    nombre: string;
  };
  segmento: TipoSegmento;
  total_compras: number;
  monto_total_gastado: string | number;
  ticket_promedio: string | number;
  ultima_compra: string | null;
  actualizado_en: string;
}

export interface MetricaSegmento {
  total: number;
  porcentaje: number;
  ticket_promedio: string | number;
}

export interface ResumenSegmentacion {
  total_clientes: number;
  segmentos: Record<TipoSegmento, MetricaSegmento>;
}

export interface SegmentacionResponse {
  clientes: ClienteSegmentado[];
  resumen: ResumenSegmentacion;
}

export interface ReglaSegmentacion {
  id: number;
  tienda_id: number;
  dias_inactividad: number;
  min_compras_frecuente: number;
  umbral_alto_valor: string | number;
  fecha_actualizacion: string;
}

export interface ReglaSegmentacionPayload {
  dias_inactividad: number;
  min_compras_frecuente: number;
  umbral_alto_valor: number;
}

export interface CampanaSegmentoPayload {
  segmento: TipoSegmento;
  nombre: string;
  mensaje: string;
  descuento_porcentaje: number;
  codigo_cupon?: string;
  fecha_expiracion?: string;
}

export interface CampanaSegmentoResultado {
  mensaje: string;
  campana_id: number;
  segmento: TipoSegmento;
  destinatarios: number;
  enviados: number;
  fallidos: number;
  codigo_cupon: string | null;
}
