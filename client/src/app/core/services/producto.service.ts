import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  Categoria,
  Producto,
  VarianteProducto,
  CrearProductoPayload,
  CrearVariantePayload
} from '../models/producto.model';

export type { Categoria, Producto, VarianteProducto, CrearProductoPayload, CrearVariantePayload };

@Injectable({
  providedIn: 'root'
})
export class ProductoService {
  private readonly apiUrl = `${environment.apiUrl}/tiendas`;

  constructor(private readonly http: HttpClient) {}

  listarCategorias(tiendaId: number): Observable<Categoria[]> {
    return this.http.get<Categoria[]>(`${this.apiUrl}/${tiendaId}/categorias/`);
  }

  listar(tiendaId?: number): Observable<Producto[]> {
    if (tiendaId !== undefined) {
      return this.http.get<Producto[]>(`${this.apiUrl}/${tiendaId}/productos/`);
    }
    return this.http.get<Producto[]>(`${this.apiUrl}/productos/`);
  }

  obtener(idOrTiendaId: number, productoId?: number): Observable<Producto> {
    if (productoId !== undefined) {
      return this.http.get<Producto>(`${this.apiUrl}/${idOrTiendaId}/productos/${productoId}/`);
    }
    return this.http.get<Producto>(`${this.apiUrl}/productos/${idOrTiendaId}/`);
  }

  crear(tiendaId: number, data: FormData): Observable<Producto> {
    return this.http.post<Producto>(`${this.apiUrl}/${tiendaId}/productos/`, data);
  }

  actualizar(tiendaIdOrId: number, idOrData: any, data?: any): Observable<Producto> {
    if (data !== undefined) {
      // Firma: actualizar(tiendaId, productoId, data)
      return this.http.patch<Producto>(`${this.apiUrl}/${tiendaIdOrId}/productos/${idOrData}/`, data);
    }
    // Firma retrocompatible: actualizar(productoId, data)
    return this.http.patch<Producto>(`${this.apiUrl}/productos/${tiendaIdOrId}/`, idOrData);
  }

  eliminar(tiendaIdOrId: number, productoId?: number): Observable<any> {
    if (productoId !== undefined) {
      // Firma: eliminar(tiendaId, productoId)
      return this.http.delete(`${this.apiUrl}/${tiendaIdOrId}/productos/${productoId}/`);
    }
    // Firma retrocompatible: eliminar(productoId)
    return this.http.delete(`${this.apiUrl}/productos/${tiendaIdOrId}/`);
  }
}
