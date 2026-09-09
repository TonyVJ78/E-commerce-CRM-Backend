import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  AuditoriaService,
  BitacoraAcceso,
  LogAuditoria,
  FiltrosBitacora,
  FiltrosLogs
} from '../../../core/services/auditoria.service';

type Pestania = 'accesos' | 'cambios';

const PAGE_SIZE = 15;

@Component({
  selector: 'app-auditoria',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './auditoria.component.html',
  styleUrls: ['./auditoria.component.css']
})
export class AuditoriaComponent implements OnInit {
  pestania: Pestania = 'accesos';

  // Filtros compartidos
  filtroUsuario = '';
  filtroFechaDesde = '';
  filtroFechaHasta = '';
  // Filtros propios de cada pestaña
  filtroIp = '';
  filtroExitoso = '';   // '' | 'true' | 'false'
  filtroTabla = '';
  filtroAccion = '';

  accesos: BitacoraAcceso[] = [];
  cambios: LogAuditoria[] = [];

  total = 0;
  pagina = 1;
  readonly pageSize = PAGE_SIZE;

  loading = false;
  errorMessage = '';

  readonly acciones = ['CREAR', 'ACTUALIZAR', 'ELIMINAR', 'CERRAR_SESION'];

  constructor(private auditoriaService: AuditoriaService) {}

  ngOnInit(): void {
    this.cargar();
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.total / this.pageSize));
  }

  cambiarPestania(p: Pestania): void {
    if (this.pestania === p) return;
    this.pestania = p;
    this.pagina = 1;
    this.errorMessage = '';
    this.cargar();
  }

  aplicarFiltros(): void {
    this.pagina = 1;
    this.cargar();
  }

  limpiarFiltros(): void {
    this.filtroUsuario = '';
    this.filtroFechaDesde = '';
    this.filtroFechaHasta = '';
    this.filtroIp = '';
    this.filtroExitoso = '';
    this.filtroTabla = '';
    this.filtroAccion = '';
    this.pagina = 1;
    this.cargar();
  }

  paginaAnterior(): void {
    if (this.pagina > 1) {
      this.pagina--;
      this.cargar();
    }
  }

  paginaSiguiente(): void {
    if (this.pagina < this.totalPaginas) {
      this.pagina++;
      this.cargar();
    }
  }

  cargar(): void {
    this.loading = true;
    this.errorMessage = '';

    if (this.pestania === 'accesos') {
      const filtros: FiltrosBitacora = {
        usuario: this.filtroUsuario || undefined,
        ip: this.filtroIp || undefined,
        exitoso: this.filtroExitoso === '' ? undefined : this.filtroExitoso === 'true',
        fecha_desde: this.filtroFechaDesde || undefined,
        fecha_hasta: this.filtroFechaHasta || undefined,
        page: this.pagina,
        page_size: this.pageSize
      };
      this.auditoriaService.listarBitacora(filtros).subscribe({
        next: (res) => {
          this.accesos = res.results;
          this.total = res.count;
          this.loading = false;
        },
        error: (err) => this.manejarError(err)
      });
    } else {
      const filtros: FiltrosLogs = {
        usuario: this.filtroUsuario || undefined,
        tabla: this.filtroTabla || undefined,
        accion: this.filtroAccion || undefined,
        fecha_desde: this.filtroFechaDesde || undefined,
        fecha_hasta: this.filtroFechaHasta || undefined,
        page: this.pagina,
        page_size: this.pageSize
      };
      this.auditoriaService.listarLogs(filtros).subscribe({
        next: (res) => {
          this.cambios = res.results;
          this.total = res.count;
          this.loading = false;
        },
        error: (err) => this.manejarError(err)
      });
    }
  }

  private manejarError(err: any): void {
    this.loading = false;
    this.total = 0;
    this.accesos = [];
    this.cambios = [];
    if (err?.status === 403) {
      this.errorMessage = 'No tienes permiso para consultar la bitácora.';
    } else {
      this.errorMessage = 'No se pudo cargar la bitácora. Intenta de nuevo.';
    }
  }

  etiquetaAccion(accion: string): string {
    const mapa: Record<string, string> = {
      CREAR: 'Creación',
      ACTUALIZAR: 'Actualización',
      ELIMINAR: 'Eliminación',
      CERRAR_SESION: 'Cierre de sesión'
    };
    return mapa[accion] ?? accion;
  }
}
