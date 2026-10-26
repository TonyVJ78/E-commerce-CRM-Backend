import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  CampanaSegmentoPayload,
  CampanaSegmentoResultado,
  ReglaSegmentacion,
  ReglaSegmentacionPayload,
  ResumenSegmentacion,
  SegmentacionResponse,
  TipoSegmento,
} from '../models/segmentacion.model';

@Injectable({ providedIn: 'root' })
export class SegmentacionService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  listarClientes(
    tiendaId: number,
    segmento = '',
    busqueda = '',
  ): Observable<SegmentacionResponse> {
    let params = new HttpParams();
    if (segmento) params = params.set('segmento', segmento);
    if (busqueda) params = params.set('q', busqueda);
    return this.http.get<SegmentacionResponse>(
      `${this.apiUrl}/tiendas/${tiendaId}/clientes/segmentacion/`,
      { params },
    );
  }

  obtenerMetricas(tiendaId: number): Observable<ResumenSegmentacion> {
    return this.listarClientes(tiendaId).pipe(map((response) => response.resumen));
  }

  recalcular(tiendaId: number): Observable<ResumenSegmentacion> {
    return this.http.post<ResumenSegmentacion>(
      `${this.apiUrl}/tiendas/${tiendaId}/clientes/segmentacion/recalcular/`,
      {},
    );
  }

  obtenerReglas(tiendaId: number): Observable<ReglaSegmentacion> {
    return this.http.get<ReglaSegmentacion>(
      `${this.apiUrl}/tiendas/${tiendaId}/clientes/segmentacion/reglas/`,
    );
  }

  actualizarReglas(
    tiendaId: number,
    reglas: Partial<ReglaSegmentacionPayload>,
  ): Observable<ReglaSegmentacion> {
    return this.http.patch<ReglaSegmentacion>(
      `${this.apiUrl}/tiendas/${tiendaId}/clientes/segmentacion/reglas/`,
      reglas,
    );
  }

  enviarCampana(
    tiendaId: number,
    campana: CampanaSegmentoPayload,
  ): Observable<CampanaSegmentoResultado> {
    return this.http.post<CampanaSegmentoResultado>(
      `${this.apiUrl}/tiendas/${tiendaId}/crm/campanas-segmento/`,
      campana,
    );
  }

  readonly segmentos: TipoSegmento[] = ['ALTO_VALOR', 'FRECUENTE', 'NUEVO', 'INACTIVO'];
}
