import { CommonModule, DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, finalize, switchMap } from 'rxjs';
import { Tienda } from '../../../core/models';
import {
  CampanaSegmentoPayload,
  ClienteSegmentado,
  ReglaSegmentacion,
  ResumenSegmentacion,
  TipoSegmento,
} from '../../../core/models/segmentacion.model';
import { SegmentacionService } from '../../../core/services/segmentacion.service';
import { TiendaService } from '../../../core/services/tienda.service';

const SEGMENTOS: TipoSegmento[] = ['ALTO_VALOR', 'FRECUENTE', 'NUEVO', 'INACTIVO'];

@Component({
  selector: 'app-segmentacion-clientes',
  standalone: true,
  imports: [CommonModule, DatePipe, ReactiveFormsModule, RouterLink],
  templateUrl: './segmentacion-clientes.component.html',
  styleUrl: './segmentacion-clientes.component.scss',
})
export class SegmentacionClientesComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder).nonNullable;
  private readonly destroyRef = inject(DestroyRef);
  private readonly tiendaService = inject(TiendaService);
  private readonly segmentacionService = inject(SegmentacionService);
  private consultaId = 0;
  private cargaReglasId = 0;

  readonly tiendas = signal<Tienda[]>([]);
  readonly tiendaSeleccionadaId = signal<number | null>(null);
  readonly clientes = signal<ClienteSegmentado[]>([]);
  readonly resumen = signal<ResumenSegmentacion | null>(null);
  readonly cargando = signal(true);
  readonly recalculando = signal(false);
  readonly guardandoReglas = signal(false);
  readonly enviandoCampana = signal(false);
  readonly mostrarReglas = signal(false);
  readonly mostrarCampana = signal(false);
  readonly error = signal<string | null>(null);
  readonly exito = signal<string | null>(null);
  readonly segmentos = SEGMENTOS;

  readonly filtroSegmento = this.formBuilder.control('');
  readonly busqueda = this.formBuilder.control('');
  readonly reglasForm = this.formBuilder.group({
    dias_inactividad: [60, [Validators.required, Validators.min(1)]],
    min_compras_frecuente: [3, [Validators.required, Validators.min(1)]],
    umbral_alto_valor: [1000, [Validators.required, Validators.min(0.01)]],
  });
  readonly campanaForm = this.formBuilder.group({
    segmento: ['INACTIVO' as TipoSegmento, Validators.required],
    nombre: ['', [Validators.required, Validators.maxLength(100)]],
    mensaje: [''],
    descuento_porcentaje: [0, [Validators.min(0), Validators.max(100)]],
    codigo_cupon: [''],
    fecha_expiracion: [''],
  });

  ngOnInit(): void {
    this.filtroSegmento.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.cargarSegmentacion());
    this.busqueda.valueChanges
      .pipe(debounceTime(250), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.cargarSegmentacion());

    this.tiendaService.listar().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (tiendas) => {
        this.tiendas.set(tiendas || []);
        if (tiendas?.length) {
          this.seleccionarTienda(tiendas[0].id);
        } else {
          this.cargando.set(false);
        }
      },
      error: (err: unknown) => {
        this.cargando.set(false);
        this.error.set(this.mensajeError(err, 'No se pudieron cargar tus tiendas.'));
      },
    });
  }

  seleccionarTienda(tiendaId: number): void {
    this.tiendaSeleccionadaId.set(tiendaId);
    this.limpiarMensajes();
    this.cargarReglas(tiendaId);
    this.cargarSegmentacion();
  }

  toggleReglas(): void {
    this.mostrarReglas.update((value) => !value);
  }

  toggleCampana(): void {
    this.mostrarCampana.update((value) => !value);
  }

  cargarSegmentacion(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId) return;

    const consulta = ++this.consultaId;
    this.cargando.set(true);
    this.error.set(null);
    this.segmentacionService
      .listarClientes(
        tiendaId,
        this.filtroSegmento.value,
        this.busqueda.value.trim(),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (consulta !== this.consultaId) return;
          this.clientes.set(response.clientes);
          this.resumen.set(response.resumen);
          this.cargando.set(false);
        },
        error: (err: unknown) => {
          if (consulta !== this.consultaId) return;
          this.cargando.set(false);
          this.error.set(this.mensajeError(err, 'No se pudo cargar la segmentación.'));
        },
      });
  }

  recalcular(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId || this.recalculando()) return;
    this.recalculando.set(true);
    this.limpiarMensajes();
    this.segmentacionService
      .recalcular(tiendaId)
      .pipe(
        finalize(() => this.recalculando.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resumen) => {
          this.resumen.set(resumen);
          this.exito.set('La segmentación se recalculó correctamente.');
          this.cargarSegmentacion();
        },
        error: (err: unknown) => {
          this.error.set(this.mensajeError(err, 'No se pudo recalcular la segmentación.'));
        },
      });
  }

  cargarReglas(tiendaId: number): void {
    const carga = ++this.cargaReglasId;
    this.segmentacionService
      .obtenerReglas(tiendaId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (reglas: ReglaSegmentacion) => {
          if (carga !== this.cargaReglasId) return;
          this.reglasForm.setValue({
            dias_inactividad: reglas.dias_inactividad,
            min_compras_frecuente: reglas.min_compras_frecuente,
            umbral_alto_valor: Number(reglas.umbral_alto_valor),
          });
        },
        error: (err: unknown) => {
          if (carga !== this.cargaReglasId) return;
          this.error.set(this.mensajeError(err, 'No se pudieron cargar las reglas.'));
        },
      });
  }

  guardarReglas(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId || this.reglasForm.invalid || this.guardandoReglas()) {
      this.reglasForm.markAllAsTouched();
      return;
    }

    this.guardandoReglas.set(true);
    this.limpiarMensajes();
    this.segmentacionService
      .actualizarReglas(tiendaId, this.reglasForm.getRawValue())
      .pipe(
        switchMap(() => this.segmentacionService.recalcular(tiendaId)),
        finalize(() => this.guardandoReglas.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resumen) => {
          this.resumen.set(resumen);
          this.mostrarReglas.set(false);
          this.exito.set('Reglas guardadas y segmentos recalculados.');
          this.cargarSegmentacion();
        },
        error: (err: unknown) => {
          this.error.set(this.mensajeError(err, 'No se pudieron guardar las reglas.'));
        },
      });
  }

  enviarCampana(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId || this.campanaForm.invalid || this.enviandoCampana()) {
      this.campanaForm.markAllAsTouched();
      return;
    }

    const valores = this.campanaForm.getRawValue();
    const payload: CampanaSegmentoPayload = {
      segmento: valores.segmento,
      nombre: valores.nombre.trim(),
      mensaje: valores.mensaje.trim(),
      descuento_porcentaje: Number(valores.descuento_porcentaje),
      ...(valores.codigo_cupon.trim() ? { codigo_cupon: valores.codigo_cupon.trim() } : {}),
      ...(valores.fecha_expiracion ? { fecha_expiracion: valores.fecha_expiracion } : {}),
    };

    this.enviandoCampana.set(true);
    this.limpiarMensajes();
    this.segmentacionService
      .enviarCampana(tiendaId, payload)
      .pipe(
        finalize(() => this.enviandoCampana.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resultado) => {
          this.mostrarCampana.set(false);
          this.exito.set(
            `${resultado.mensaje} ${resultado.enviados} correos enviados; ${resultado.fallidos} fallidos.`,
          );
          this.campanaForm.reset({
            segmento: 'INACTIVO',
            nombre: '',
            mensaje: '',
            descuento_porcentaje: 0,
            codigo_cupon: '',
            fecha_expiracion: '',
          });
        },
        error: (err: unknown) => {
          this.error.set(this.mensajeError(err, 'No se pudo procesar la campaña.'));
        },
      });
  }

  nombreSegmento(segmento: TipoSegmento): string {
    return {
      ALTO_VALOR: 'Alto valor',
      FRECUENTE: 'Frecuente',
      INACTIVO: 'Inactivo',
      NUEVO: 'Nuevo',
    }[segmento];
  }

  claseSegmento(segmento: TipoSegmento): string {
    return `segmento-badge segmento-badge--${segmento.toLowerCase().replace('_', '-')}`;
  }

  formatoMoneda(valor: number | string | null | undefined): string {
    return new Intl.NumberFormat('es-BO', {
      style: 'currency',
      currency: 'BOB',
      maximumFractionDigits: 2,
    }).format(Number(valor) || 0);
  }

  limpiarMensajes(): void {
    this.error.set(null);
    this.exito.set(null);
  }

  private mensajeError(error: unknown, fallback: string): string {
    if (typeof error === 'object' && error !== null && 'error' in error) {
      const response = (error as { error?: { detail?: string; non_field_errors?: string[] } }).error;
      return response?.detail || response?.non_field_errors?.[0] || fallback;
    }
    return fallback;
  }
}
