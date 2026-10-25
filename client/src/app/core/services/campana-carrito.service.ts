import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  CampanaCarrito,
  ResumenCampanaResponse,
  CarritoAbandonadoItem,
} from '../models/campana-carrito.model';

@Injectable({
  providedIn: 'root',
})
export class CampanaCarritoService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = environment.apiUrl;

  /**
   * Obtiene la configuración de campaña y métricas para una tienda (CU-27).
   */
  obtenerCampana(tiendaId: number): Observable<ResumenCampanaResponse> {
    return this.http.get<ResumenCampanaResponse>(`${this.apiBase}/tiendas/${tiendaId}/campana-carrito/`);
  }

  /**
   * Guarda o actualiza los parámetros de la campaña de carrito abandonado.
   */
  guardarCampana(
    tiendaId: number,
    data: Partial<CampanaCarrito>
  ): Observable<{ mensaje: string; campana: CampanaCarrito }> {
    return this.http.put<{ mensaje: string; campana: CampanaCarrito }>(
      `${this.apiBase}/tiendas/${tiendaId}/campana-carrito/`,
      data
    );
  }

  /**
   * Lista los carritos inactivos detectados con productos de la tienda.
   */
  listarCarritosAbandonados(tiendaId: number): Observable<CarritoAbandonadoItem[]> {
    return this.http.get<CarritoAbandonadoItem[]>(
      `${this.apiBase}/tiendas/${tiendaId}/carritos-abandonados/`
    );
  }

  /**
   * Envía un correo de prueba de la campaña a la dirección registrada de la tienda.
   */
  dispararPrueba(
    tiendaId: number
  ): Observable<{ success: boolean; enviado: boolean; destinatario: string; mensaje: string }> {
    return this.http.post<{ success: boolean; enviado: boolean; destinatario: string; mensaje: string }>(
      `${this.apiBase}/tiendas/${tiendaId}/campana-carrito/disparar-prueba/`,
      {}
    );
  }
}
