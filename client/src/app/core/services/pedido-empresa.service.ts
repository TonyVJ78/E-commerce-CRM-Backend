import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  CambiarEstadoPedidoPayload,
  EstadoPedido,
  PedidoRecibidoDetalle,
  PedidosRecibidosResponse,
} from '../models/pedido.model';

/** CU-22 — Gestionar pedidos recibidos por las tiendas de la empresa. */
@Injectable({ providedIn: 'root' })
export class PedidoEmpresaService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/tiendas`;

  listar(tiendaId: number, filtros: { estado?: EstadoPedido | ''; q?: string } = {}): Observable<PedidosRecibidosResponse> {
    let params = new HttpParams();
    if (filtros.estado) {
      params = params.set('estado', filtros.estado);
    }
    if (filtros.q?.trim()) {
      params = params.set('q', filtros.q.trim());
    }
    return this.http.get<PedidosRecibidosResponse>(`${this.apiUrl}/${tiendaId}/pedidos/`, { params });
  }

  detalle(tiendaId: number, pedidoId: number): Observable<PedidoRecibidoDetalle> {
    return this.http.get<PedidoRecibidoDetalle>(`${this.apiUrl}/${tiendaId}/pedidos/${pedidoId}/`);
  }

  cambiarEstado(tiendaId: number, pedidoId: number, payload: CambiarEstadoPedidoPayload): Observable<PedidoRecibidoDetalle> {
    return this.http.patch<PedidoRecibidoDetalle>(`${this.apiUrl}/${tiendaId}/pedidos/${pedidoId}/estado/`, payload);
  }
}
