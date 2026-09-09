export interface Categoria {
  id: number;
  nombre: string;
  categoria_padre: number | null;
}

export interface VarianteProducto {
  id: number;
  sku: string;
  nombre: string;
  precio: string | number;
  precio_oferta: string | number | null;
  stock: number;
  stock_minimo: number;
  atributos: Record<string, string>;
  activa: boolean;
}

export interface ProductoImagen {
  url: string;
  public_id: string;
}

export interface Producto {
  id: number;
  tienda: number;
  tienda_nombre?: string;
  categoria_id?: number | null;
  categoria?: string;
  nombre: string;
  slug: string;
  descripcion?: string;
  etiquetas?: string[];
  imagenes?: ProductoImagen[];
  imagen_url?: string;
  activo?: boolean;
  creado?: string;
  actualizado?: string;
  variantes?: VarianteProducto[];
  stock_total?: number;
  agotado?: boolean;
  en_stock?: boolean;
  // Campos de conveniencia basados en variante principal:
  precio?: number | string;
  stock?: number;
}

export interface CrearVariantePayload {
  sku: string;
  nombre?: string;
  precio: number;
  precio_oferta?: number | null;
  stock: number;
  stock_minimo?: number;
  atributos?: Record<string, string>;
  activa?: boolean;
}

export interface CrearProductoPayload {
  nombre: string;
  categoria_id?: number | null;
  descripcion?: string;
  etiquetas?: string[];
  activo?: boolean;
  variantes: CrearVariantePayload[];
}