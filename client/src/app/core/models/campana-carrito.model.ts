export interface CampanaCarrito {
  id: number;
  tienda_id: number;
  tienda_nombre: string;
  activo: boolean;
  horas_inactividad: number;
  asunto_email: string;
  mensaje_email: string;
  descuento_porcentaje: number;
  codigo_cupon?: string | null;
  fecha_actualizacion: string;
}

export interface MetricasCampana {
  carritos_detectados: number;
  valor_en_riesgo: number;
  emails_enviados: number;
  carritos_recuperados: number;
  tasa_conversion: number;
}

export interface ResumenCampanaResponse {
  campana: CampanaCarrito;
  metricas: MetricasCampana;
}

export interface CarritoItemDetalle {
  id: number;
  producto_nombre: string;
  variante: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  imagen?: string | null;
}

export interface CarritoAbandonadoItem {
  id: number;
  cliente: {
    id: number;
    email: string;
    nombre: string;
  };
  fecha_creacion: string;
  horas_inactivo: number;
  total_items: number;
  monto_total: number;
  items: CarritoItemDetalle[];
  notificado: boolean;
  fecha_notificacion?: string | null;
  recuperado: boolean;
}
