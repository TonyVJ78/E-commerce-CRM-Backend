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

  listarTodosLosProductos(filtros?: { categoria?: number; tienda?: number; q?: string }): Observable<ProductoCatalogo[]> {
    let params = new HttpParams();
    if (filtros?.categoria) {
      params = params.set('categoria', filtros.categoria.toString());
    }
    if (filtros?.tienda) {
      params = params.set('tienda', filtros.tienda.toString());
    }
    if (filtros?.q) {
      params = params.set('q', filtros.q.trim());
    }
    return this.http.get<ProductoCatalogo[]>(`${this.apiUrl}/productos/`, { params });
  }

  listarProductos(tiendaId: number): Observable<ProductoCatalogo[]> {
    return this.http.get<ProductoCatalogo[]>(
      `${this.apiUrl}/tiendas/${tiendaId}/productos/`
    );
  }
}
