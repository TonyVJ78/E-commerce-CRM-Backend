import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  TiendaCatalogo,
  VarianteCatalogo,
  ProductoCatalogo,
  CategoriaCatalogo
} from '../models/catalogo.model';

export type { TiendaCatalogo, VarianteCatalogo, ProductoCatalogo, CategoriaCatalogo };

@Injectable({ providedIn: 'root' })
export class CatalogoService {
  private readonly apiUrl = `${environment.apiUrl}/catalogo`;

  constructor(private readonly http: HttpClient) {}

  listarTiendas(): Observable<TiendaCatalogo[]> {
    return this.http.get<TiendaCatalogo[]>(`${this.apiUrl}/tiendas/`);
  }

  listarCategorias(tiendaId?: number): Observable<CategoriaCatalogo[]> {
    let params = new HttpParams();
    if (tiendaId !== undefined && tiendaId !== null) {
      params = params.set('tienda', tiendaId.toString());
    }
    return this.http.get<CategoriaCatalogo[]>(`${this.apiUrl}/categorias/`, { params });
  }

  listarTodosLosProductos(filtros?: {
    categoria?: number;
    categoria_nombre?: string;
    tienda?: number;
    q?: string;
    precio_min?: number;
    precio_max?: number;
    en_stock?: boolean;
    orden?: string;
  }): Observable<ProductoCatalogo[]> {
    let params = new HttpParams();
    if (filtros?.categoria) {
      params = params.set('categoria', filtros.categoria.toString());
    }
    if (filtros?.categoria_nombre) {
      params = params.set('categoria_nombre', filtros.categoria_nombre.trim());
    }
    if (filtros?.tienda) {
      params = params.set('tienda', filtros.tienda.toString());
    }
    if (filtros?.q) {
      params = params.set('q', filtros.q.trim());
    }
    if (filtros?.precio_min !== undefined && filtros?.precio_min !== null) {
      params = params.set('precio_min', filtros.precio_min.toString());
    }
    if (filtros?.precio_max !== undefined && filtros?.precio_max !== null) {
      params = params.set('precio_max', filtros.precio_max.toString());
    }
    if (filtros?.en_stock) {
      params = params.set('en_stock', 'true');
    }
    if (filtros?.orden) {
      params = params.set('orden', filtros.orden);
    }
    return this.http.get<ProductoCatalogo[]>(`${this.apiUrl}/productos/`, { params });
  }

  obtenerProducto(productoId: number): Observable<ProductoCatalogo> {
    return this.http.get<ProductoCatalogo>(`${this.apiUrl}/productos/${productoId}/`);
  }


  listarProductos(tiendaId: number): Observable<ProductoCatalogo[]> {
    return this.http.get<ProductoCatalogo[]>(
      `${this.apiUrl}/tiendas/${tiendaId}/productos/`
    );
  }
}
