import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  Tienda,
  CreateTiendaData,
  DashboardMetrics,
  VentaDia,
  TiendaIdentidad,
  TiendaIdentidadUpdate,
  SlugDisponibilidad
} from '../models/tienda.model';

export type {
  Tienda,
  CreateTiendaData,
  DashboardMetrics,
  VentaDia,
  TiendaIdentidad,
  TiendaIdentidadUpdate,
  SlugDisponibilidad
};

@Injectable({
  providedIn: 'root'
})
export class TiendaService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/tiendas`;

  listar(): Observable<Tienda[]> {
    return this.http.get<Tienda[]>(`${this.apiUrl}/`);
  }

  crear(data: CreateTiendaData): Observable<Tienda> {
    return this.http.post<Tienda>(`${this.apiUrl}/`, data);
  }

  obtenerIdentidad(tiendaId: number): Observable<TiendaIdentidad> {
    return this.http.get<TiendaIdentidad>(`${this.apiUrl}/${tiendaId}/identidad/`);
  }

  actualizarIdentidad(
    tiendaId: number,
    data: TiendaIdentidadUpdate,
    logo?: File
  ): Observable<TiendaIdentidad> {
    const payload = new FormData();
    payload.append('slug', data.slug);
    payload.append('color_primario', data.color_primario);
    if (logo) {
      payload.append('logo', logo, logo.name);
    }
    return this.http.patch<TiendaIdentidad>(
      `${this.apiUrl}/${tiendaId}/identidad/`,
      payload
    );
  }

  verificarSlug(tiendaId: number, slug: string): Observable<SlugDisponibilidad> {
    const params = new HttpParams().set('slug', slug);
    return this.http.get<SlugDisponibilidad>(
      `${this.apiUrl}/${tiendaId}/identidad/slug-disponible/`,
      { params }
    );
  }

  getDashboardMetrics(): Observable<DashboardMetrics> {
    return this.http.get<DashboardMetrics>(`${this.apiUrl}/dashboard/`);
  }
}
