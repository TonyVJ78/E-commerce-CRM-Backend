import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  TicketSoporte,
  MensajeTicket,
  FiltrosTickets,
  CrearTicketRequest,
  TiendaTicketsResponse,
} from '../models/soporte.model';

@Injectable({
  providedIn: 'root',
})
export class SoporteService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = environment.apiUrl;

  /**
   * Crea un nuevo ticket de soporte o reclamo como cliente (CU-26).
   */
  crearTicket(req: CrearTicketRequest): Observable<TicketSoporte> {
    return this.http.post<TicketSoporte>(`${this.apiBase}/soporte/tickets/`, req);
  }

  /**
   * Lista los tickets registrados por el cliente autenticado.
   */
  listarMisTickets(): Observable<TicketSoporte[]> {
    return this.http.get<TicketSoporte[]>(`${this.apiBase}/soporte/tickets/mis-tickets/`);
  }

  /**
   * Obtiene el detalle de un ticket con todo su historial de mensajes.
   */
  obtenerDetalle(id: number): Observable<TicketSoporte> {
    return this.http.get<TicketSoporte>(`${this.apiBase}/soporte/tickets/${id}/`);
  }

  /**
   * Agrega un mensaje o respuesta al hilo del ticket.
   */
  responderTicket(id: number, contenido: string, archivoAdjunto?: string | null): Observable<MensajeTicket> {
    const payload: { contenido: string; archivo_adjunto?: string | null } = { contenido };
    if (archivoAdjunto) {
      payload.archivo_adjunto = archivoAdjunto;
    }
    return this.http.post<MensajeTicket>(`${this.apiBase}/soporte/tickets/${id}/responder/`, payload);
  }

  /**
   * Lista los tickets recibidos por una tienda con filtros y metricas KPI para el vendedor.
   */
  listarPorTienda(tiendaId: number, filtros?: FiltrosTickets): Observable<TiendaTicketsResponse> {
    let params = new HttpParams();
    if (filtros?.estado) {
      params = params.set('estado', filtros.estado);
    }
    if (filtros?.prioridad) {
      params = params.set('prioridad', filtros.prioridad);
    }
    if (filtros?.tipo) {
      params = params.set('tipo', filtros.tipo);
    }
    return this.http.get<TiendaTicketsResponse>(`${this.apiBase}/tiendas/${tiendaId}/tickets/`, { params });
  }

  /**
   * Actualiza el estado del ticket desde el panel del vendedor.
   */
  actualizarEstado(tiendaId: number, ticketId: number, estado: string): Observable<TicketSoporte> {
    return this.http.patch<TicketSoporte>(`${this.apiBase}/tiendas/${tiendaId}/tickets/${ticketId}/estado/`, {
      estado,
    });
  }
}
