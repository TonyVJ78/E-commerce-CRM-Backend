import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  Paginated,
  BitacoraAcceso,
  LogAuditoria,
  FiltrosBitacora,
  FiltrosLogs
} from '../models';

export type {
  Paginated,
  BitacoraAcceso,
  LogAuditoria,
  FiltrosBitacora,
  FiltrosLogs
};

@Injectable({
  providedIn: 'root'
})
export class AuditoriaService {
  private readonly apiUrl = `${environment.apiUrl}/auditoria`;

  constructor(private readonly http: HttpClient) {}

  private toParams(filtros: object): HttpParams {
    let params = new HttpParams();
    for (const [clave, valor] of Object.entries(filtros)) {
      if (valor !== undefined && valor !== null && `${valor}` !== '') {
        params = params.set(clave, `${valor}`);
      }
    }
    return params;
  }

  listarBitacora(filtros: FiltrosBitacora = {}): Observable<Paginated<BitacoraAcceso>> {
    return this.http.get<Paginated<BitacoraAcceso>>(`${this.apiUrl}/bitacora/`, {
      params: this.toParams(filtros)
    });
  }

  listarLogs(filtros: FiltrosLogs = {}): Observable<Paginated<LogAuditoria>> {
    return this.http.get<Paginated<LogAuditoria>>(`${this.apiUrl}/logs/`, {
      params: this.toParams(filtros)
    });
  }
}
