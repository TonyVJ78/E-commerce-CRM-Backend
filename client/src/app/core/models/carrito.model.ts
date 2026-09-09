export interface AgregarItemCarritoRequest {
  tienda_id: number;
  variante_id: number;
}

export interface ItemCarritoCreado {
  id: number;
  carrito_id: number;
  tienda_id: number;
  variante_id: number;
  producto_id: number;
  cantidad: number;
}

export interface ItemCarritoDetalle {
  id: number;
  carrito_id: number;
  tienda_id: number;
  tienda_nombre: string;
  producto_id: number;
  producto_nombre: string;
  producto_imagen: string;
  variante_id: number;
  variante_nombre: string;
  variante_sku: string;
  precio_unitario: string;
  cantidad: number;
  subtotal: string;
  stock_disponible: number;
}

export interface CarritoDetalle {
  id: number;
  tienda_id: number;
  tienda_nombre: string;
  fecha_creacion: string;
  items: ItemCarritoDetalle[];
  cantidad_items: number;
  total: string;
}

export interface CarritoResponse {
  carritos: CarritoDetalle[];
  total_items: number;
  total_global: string;
}

export interface ItemCarrito {
  id: number;
  tienda: number;
  carrito: number;
  variante: number;
  cantidad: number;
  agregado_en?: string;
}

export interface CarritoResumen {
  id: number;
  tienda_id: number;
  items_count: number;
}
