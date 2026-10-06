/** Ciclo de vida de un pedido (CU-22), compartido con "Mis pedidos" (CU-20). */
export type EstadoPedido = 'pendiente' | 'procesado' | 'enviado' | 'entregado' | 'cancelado';

export const FLUJO_PEDIDO: EstadoPedido[] = ['pendiente', 'procesado', 'enviado', 'entregado'];

export const ETIQUETA_ESTADO_PEDIDO: Record<EstadoPedido, string> = {
  pendiente: 'Pendiente',
  procesado: 'Procesado',
  enviado: 'Enviado',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
};

export interface ClientePedido {
  id: number;
  email: string;
  nombre: string;
}

export interface PedidoRecibido {
  id: number;
  cliente: ClientePedido;
  estado: EstadoPedido;
  estado_etiqueta: string;
  siguientes_estados: EstadoPedido[];
  fecha: string | null;
  total: string;
  cantidad_items: number | null;
}

export interface ItemPedidoDetalle {
  id: number;
  producto_id: number | null;
  producto_nombre: string;
  producto_imagen: string;
  variante_id: number | null;
  variante_nombre: string;
  variante_sku: string;
  cantidad: number;
  precio_unitario: string;
  subtotal: string;
}

export interface HistorialEstadoPedido {
  estado: EstadoPedido;
  estado_etiqueta: string;
  fecha: string | null;
}

export interface PagoPedido {
  metodo: string;
  estado: string;
  monto: string;
  referencia: string;
  fecha: string | null;
}

export interface EnvioPedido {
  transportista: string;
  numero_seguimiento: string;
  fecha_envio: string | null;
  fecha_entrega: string | null;
  direccion: string;
}

export interface PedidoRecibidoDetalle extends PedidoRecibido {
  subtotal: string;
  items: ItemPedidoDetalle[];
  pago: PagoPedido | null;
  envio: EnvioPedido | null;
  historial: HistorialEstadoPedido[];
  mensaje?: string;
  aviso?: string;
}

export interface PedidosRecibidosResponse {
  tienda: { id: number; nombre: string };
  conteos: Record<EstadoPedido, number>;
  total: number;
  pedidos: PedidoRecibido[];
}

export interface CambiarEstadoPedidoPayload {
  estado: EstadoPedido;
  transportista?: string;
  numero_seguimiento?: string;
}
