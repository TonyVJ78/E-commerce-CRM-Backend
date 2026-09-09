export interface Tienda {
  id: number;
  propietario: number;
  propietario_email?: string;
  nombre: string;
  slug: string;
  descripcion?: string;
  logo_url?: string;
  banner_url?: string;
  color_primario?: string;
  activa: boolean;
  creada?: string;
  fecha_creacion?: string;
}

export interface TiendaCreate {
  nombre: string;
  slug?: string;
  descripcion?: string;
  logo_url?: string;
  banner_url?: string;
  color_primario?: string;
}

export type CreateTiendaData = TiendaCreate;

export interface VentaDia {
  fecha: string;
  cantidad: number;
}

export interface DashboardVendedorMetrics {
  total_productos: number;
  productos_activos: number;
  total_pedidos: number;
  pedidos_pendientes: number;
  ingresos_totales: number;
  productos_bajo_stock: number;
  grafico_ventas: VentaDia[];
}

export type DashboardMetrics = DashboardVendedorMetrics;
