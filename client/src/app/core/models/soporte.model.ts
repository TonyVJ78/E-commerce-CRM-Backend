export interface MensajeTicket {
  id: number;
  ticket: number;
  autor: {
    id: number;
    email: string;
    nombre: string;
  };
  contenido: string;
  archivo_adjunto?: string | null;
  fecha_envio: string;
}

export interface TicketSoporte {
  id: number;
  codigo_ticket: string;
  cliente: {
    id: number;
    email: string;
    nombre: string;
  };
  tienda_id: number;
  tienda_nombre: string;
  pedido?: number | null;
  pedido_codigo?: string | null;
  tipo: 'consulta' | 'reclamo_producto' | 'demora_envio' | 'devolucion' | string;
  tipo_display: string;
  prioridad: 'baja' | 'media' | 'alta' | 'urgente' | string;
  prioridad_display: string;
  estado: 'abierto' | 'en_proceso' | 'resuelto' | 'cerrado' | string;
  estado_display: string;
  asunto: string;
  descripcion: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  fecha_resolucion?: string | null;
  mensajes?: MensajeTicket[];
  total_mensajes?: number;
}

export interface FiltrosTickets {
  estado?: string;
  prioridad?: string;
  tipo?: string;
}

export interface CrearTicketRequest {
  tienda_id?: number | null;
  pedido_id?: number | null;
  tipo: string;
  prioridad: string;
  asunto: string;
  descripcion: string;
  archivo_adjunto?: string | null;
}

export interface KpisTicketsTienda {
  total_abiertos: number;
  total_en_proceso: number;
  total_resueltos: number;
  total_tickets: number;
}

export interface TiendaTicketsResponse {
  kpis: KpisTicketsTienda;
  tickets: TicketSoporte[];
}
