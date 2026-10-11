import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  BackupItem,
  ResumenBackups,
  ResumenBackupsResponse,
  RespaldoGeneradoResponse,
  ConfigAutomatizacion
} from '../models/backup.model';

export type {
  BackupItem,
  ResumenBackups,
  ResumenBackupsResponse,
  RespaldoGeneradoResponse,
  ConfigAutomatizacion
};

@Injectable({
  providedIn: 'root'
})
export class BackupService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/admin/backups`;

  /**
   * Obtiene la lista de respaldos disponibles y el resumen de espacio en disco.
   */
  obtenerListado(): Observable<ResumenBackupsResponse> {
    return this.http.get<ResumenBackupsResponse>(`${this.apiUrl}/`);
  }

  /**
   * Ejecuta un respaldo manual transaccional en la base de datos PostgreSQL/Neon.
   */
  generarRespaldoManual(): Observable<RespaldoGeneradoResponse> {
    return this.http.post<RespaldoGeneradoResponse>(`${this.apiUrl}/generar/`, {});
  }

  /**
   * Descarga el archivo de respaldo binario (.sql.gz) de manera segura.
   */
  descargarRespaldo(nombreArchivo: string): Observable<Blob> {
    const params = new HttpParams().set('archivo', nombreArchivo);
    return this.http.get(`${this.apiUrl}/descargar/`, {
      params,
      responseType: 'blob'
    });
  }

  /**
   * Consulta la configuracion y hora de la proxima ejecucion automatica.
   */
  obtenerConfigAutomatica(): Observable<ConfigAutomatizacion> {
    return this.http.get<ConfigAutomatizacion>(`${this.apiUrl}/automatizacion/`);
  }

  /**
   * Guarda los parametros de programacion automatica y dias de retencion.
   */
  guardarConfigAutomatica(config: ConfigAutomatizacion): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/automatizacion/`, config);
  }
}
