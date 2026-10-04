import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { environment } from '../../../environments/environment';
import { ProductoCatalogo } from '../models/catalogo.model';

export type TipoInteraccionRecomendacion = 'VIEW' | 'CLICK' | 'SEARCH';

export interface InteraccionRecomendacion {
  tienda_id: number;
  tipo_interaccion: TipoInteraccionRecomendacion;
  producto_id?: number;
  termino_busqueda?: string;
}

export interface InteraccionRegistrada extends InteraccionRecomendacion {
  id: number;
  fecha: string;
}

@Injectable({ providedIn: 'root' })
export class RecomendacionService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/ia`;
  private readonly eventosRecientes = new Map<string, number>();
  private readonly dedupMs = 30_000;

  /**
   * Obtiene recomendaciones de la tienda.
   * Resiliencia: si el endpoint falla o no hay datos, retorna un arreglo vacío [] silenciosamente.
   */
  obtenerRecomendaciones(tiendaId: number, limit = 8): Observable<ProductoCatalogo[]> {
    const params = new HttpParams().set('limit', String(limit));
    return this.http.get<ProductoCatalogo[]>(
      `${this.apiUrl}/tiendas/${tiendaId}/`,
      { params }
    ).pipe(
      catchError(() => of([]))
    );
  }

  /**
   * Registra una interacción de telemetría de forma asíncrona ("fire-and-forget").
   * Deduplica eventos en una ventana de 30 segundos.
   */
  registrarInteraccion(
    data: InteraccionRecomendacion
  ): Observable<InteraccionRegistrada | null> {
    const termino = data.termino_busqueda?.trim().toLowerCase() ?? '';
    const key = [
      data.tipo_interaccion,
      data.tienda_id,
      data.producto_id ?? '',
      termino
    ].join(':');
    const now = Date.now();
    const last = this.eventosRecientes.get(key);

    if (last !== undefined && now - last < this.dedupMs) {
      return of(null);
    }

    this.eventosRecientes.set(key, now);
    return this.http.post<InteraccionRegistrada>(
      `${this.apiUrl}/eventos/`,
      { ...data, termino_busqueda: termino || undefined }
    ).pipe(
      catchError(() => of(null))
    );
  }

  /**
   * Helper "fire-and-forget": ejecuta la telemetría en segundo plano sin requerir suscripción manual
   * y sin bloquear ninguna acción o navegación del usuario.
   */
  notificarInteraccion(data: InteraccionRecomendacion): void {
    this.registrarInteraccion(data).subscribe();
  }
}
