import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface PedidoClienteItem {
  id: number;
  producto_id: number | null;
  producto_nombre: string;
  variante_nombre: string;
  cantidad: number;
  precio_unitario: string;
  subtotal: string;
}

export interface HistorialPedido {
  estado: string;
  fecha: string | null;
  observacion: string | null;
}

export interface ResenaPedido {
  id: number;
  tipo: 'producto' | 'tienda';
  producto_id: number | null;
  producto_nombre: string | null;
  tienda_id: number;
  tienda_nombre: string;
  calificacion: number;
  comentario: string;
  fecha: string | null;
}

export interface PedidoCliente {
  id: number;
  tienda_id: number;
  tienda_nombre: string;
  estado: string;
  subtotal: string;
  total: string;
  fecha: string | null;
  items: PedidoClienteItem[];
  historial?: HistorialPedido[];
  resenas?: ResenaPedido[];
}

export interface GuardarResenaPayload {
  tipo: 'producto' | 'tienda';
  producto_id?: number;
  calificacion: number;
  comentario: string;
}

@Injectable({ providedIn: 'root' })
export class PedidosClienteService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/pedidos/mis-pedidos`;

  listar(): Observable<{ pedidos: PedidoCliente[] }> {
    return this.http.get<{ pedidos: PedidoCliente[] }>(`${this.apiUrl}/`);
  }

  obtener(id: number): Observable<PedidoCliente> {
    return this.http.get<PedidoCliente>(`${this.apiUrl}/${id}/`);
  }

  guardarResena(id: number, resena: GuardarResenaPayload): Observable<ResenaPedido> {
    return this.http.post<ResenaPedido>(`${this.apiUrl}/${id}/resenas/`, resena);
  }
}
