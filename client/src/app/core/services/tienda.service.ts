import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  Tienda,
  CreateTiendaData,
  DashboardMetrics,
  VentaDia
} from '../models/tienda.model';

export type { Tienda, CreateTiendaData, DashboardMetrics, VentaDia };

@Injectable({
  providedIn: 'root'
})
export class TiendaService {
  private readonly apiUrl = `${environment.apiUrl}/tiendas`;

  constructor(private readonly http: HttpClient) {}

  listar(): Observable<Tienda[]> {
    return this.http.get<Tienda[]>(`${this.apiUrl}/`);
  }

  crear(data: CreateTiendaData): Observable<Tienda> {
    return this.http.post<Tienda>(`${this.apiUrl}/`, data);
  }

  getDashboardMetrics(): Observable<DashboardMetrics> {
    return this.http.get<DashboardMetrics>(`${this.apiUrl}/dashboard/`);
  }
}
