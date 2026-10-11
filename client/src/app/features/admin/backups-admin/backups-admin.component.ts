import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  BackupService,
  BackupItem,
  ResumenBackups,
  ConfigAutomatizacion
} from '../../../core/services/backup.service';

@Component({
  selector: 'app-backups-admin',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink],
  templateUrl: './backups-admin.component.html',
  styleUrl: './backups-admin.component.scss'
})
export class BackupsAdminComponent implements OnInit {
  private readonly backupService = inject(BackupService);

  // Estados de datos (Signals)
  readonly backups = signal<BackupItem[]>([]);
  readonly resumen = signal<ResumenBackups>({
    total_archivos: 0,
    espacio_total_mb: 0,
    ultimo_respaldo: null
  });
  readonly configAuto = signal<ConfigAutomatizacion>({
    activo: true,
    frecuencia: 'diaria',
    hora_ejecucion: '03:00',
    retencion_dias: 30,
    proxima_ejecucion: null
  });

  // Estados de interfaz reactivos (Signals)
  readonly cargando = signal<boolean>(true);
  readonly creandoRespaldo = signal<boolean>(false);
  readonly descargandoArchivo = signal<string | null>(null);
  readonly guardandoConfig = signal<boolean>(false);
  readonly mensajeExito = signal<string | null>(null);
  readonly mensajeError = signal<string | null>(null);

  // Senales computadas para KPIs y resumenes
  readonly totalArchivos = computed(() => this.resumen().total_archivos);
  readonly espacioFormateado = computed(() => `${this.resumen().espacio_total_mb.toFixed(2)} MB`);
  readonly ultimoRespaldo = computed(() => this.resumen().ultimo_respaldo);
  readonly automatizacionActiva = computed(() => this.configAuto().activo);

  ngOnInit(): void {
    this.cargarDatos();
    this.cargarConfiguracion();
  }

  cargarDatos(): void {
    this.cargando.set(true);
    this.backupService.obtenerListado().subscribe({
      next: (resp) => {
        this.backups.set(resp.backups || []);
        this.resumen.set(resp.resumen || {
          total_archivos: (resp.backups || []).length,
          espacio_total_mb: 0,
          ultimo_respaldo: null
        });
        this.cargando.set(false);
      },
      error: (err) => {
        this.cargando.set(false);
        this.mensajeError.set(
          err?.error?.detail || 'No se pudo cargar el listado de copias de seguridad.'
        );
      }
    });
  }

  cargarConfiguracion(): void {
    this.backupService.obtenerConfigAutomatica().subscribe({
      next: (config) => {
        this.configAuto.set(config);
      },
      error: () => {
        // En caso de fallo de red puntual mantiene defaults
      }
    });
  }

  generarRespaldo(): void {
    if (this.creandoRespaldo()) {
      return;
    }

    this.creandoRespaldo.set(true);
    this.limpiarMensajes();

    this.backupService.generarRespaldoManual().subscribe({
      next: (resp) => {
        this.creandoRespaldo.set(false);
        this.mensajeExito.set(
          resp.mensaje || 'Copia de seguridad generada y comprimida con exito.'
        );
        // Actualizar lista agregando el nuevo respaldo al inicio
        if (resp.backup) {
          this.backups.update(prev => [resp.backup, ...prev]);
        }
        // Recargar listado completo para recalcular espacio y KPIs
        this.cargarDatos();
      },
      error: (err) => {
        this.creandoRespaldo.set(false);
        this.mensajeError.set(
          err?.error?.mensaje || err?.error?.detail || 'Fallo critico al generar el respaldo manual.'
        );
      }
    });
  }

  descargarRespaldo(archivo: string): void {
    if (this.descargandoArchivo()) {
      return;
    }

    this.descargandoArchivo.set(archivo);
    this.limpiarMensajes();

    this.backupService.descargarRespaldo(archivo).subscribe({
      next: (blob) => {
        this.descargandoArchivo.set(null);
        // Desencadenar descarga directa en el navegador
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = archivo;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      },
      error: (err) => {
        this.descargandoArchivo.set(null);
        this.mensajeError.set(
          err?.error?.detail || `No se pudo descargar el archivo de respaldo: ${archivo}`
        );
      }
    });
  }

  guardarConfiguracion(): void {
    this.guardandoConfig.set(true);
    this.limpiarMensajes();

    this.backupService.guardarConfigAutomatica(this.configAuto()).subscribe({
      next: (resp) => {
        this.guardandoConfig.set(false);
        if (resp?.config) {
          this.configAuto.set(resp.config);
        }
        this.mensajeExito.set(
          resp?.mensaje || 'Parametros de programacion automatica guardados exitosamente.'
        );
      },
      error: (err) => {
        this.guardandoConfig.set(false);
        this.mensajeError.set(
          err?.error?.detail || 'Error al guardar los parametros de automatizacion.'
        );
      }
    });
  }

  actualizarActivo(activo: boolean): void {
    this.configAuto.update(cfg => ({ ...cfg, activo }));
  }

  actualizarFrecuencia(frecuencia: string): void {
    this.configAuto.update(cfg => ({ ...cfg, frecuencia }));
  }

  actualizarHora(hora: string): void {
    this.configAuto.update(cfg => ({ ...cfg, hora_ejecucion: hora }));
  }

  actualizarRetencion(dias: number): void {
    this.configAuto.update(cfg => ({ ...cfg, retencion_dias: Math.max(1, Number(dias) || 30) }));
  }

  limpiarMensajes(): void {
    this.mensajeExito.set(null);
    this.mensajeError.set(null);
  }
}
