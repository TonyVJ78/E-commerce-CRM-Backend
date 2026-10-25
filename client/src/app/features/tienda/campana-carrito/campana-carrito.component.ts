import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { CampanaCarritoService } from '../../../core/services/campana-carrito.service';
import { TiendaService } from '../../../core/services/tienda.service';
import {
  CampanaCarrito,
  MetricasCampana,
  CarritoAbandonadoItem,
} from '../../../core/models/campana-carrito.model';
import { Tienda } from '../../../core/models';

@Component({
  selector: 'app-campana-carrito',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './campana-carrito.component.html',
  styleUrl: './campana-carrito.component.scss',
})
export class CampanaCarritoComponent implements OnInit {
  private readonly campanaService = inject(CampanaCarritoService);
  private readonly tiendaService = inject(TiendaService);

  readonly tiendas = signal<Tienda[]>([]);
  readonly tiendaSeleccionadaId = signal<number | null>(null);

  readonly campana = signal<CampanaCarrito>({
    id: 0,
    tienda_id: 0,
    tienda_nombre: '',
    activo: false,
    horas_inactividad: 2,
    asunto_email: 'Tienes productos esperando en tu carrito',
    mensaje_email: 'Notamos que dejaste articulos seleccionados en Kantu Market. Completa tu pedido antes de que se agote el stock.',
    descuento_porcentaje: 0,
    codigo_cupon: '',
    fecha_actualizacion: '',
  });

  readonly metricas = signal<MetricasCampana>({
    carritos_detectados: 0,
    valor_en_riesgo: 0,
    emails_enviados: 0,
    carritos_recuperados: 0,
    tasa_conversion: 0,
  });

  readonly carritosAbandonados = signal<CarritoAbandonadoItem[]>([]);

  readonly cargando = signal<boolean>(true);
  readonly guardando = signal<boolean>(false);
  readonly enviandoPrueba = signal<boolean>(false);

  readonly mensajeExito = signal<string | null>(null);
  readonly mensajeError = signal<string | null>(null);

  // Senales computadas para KPIs
  readonly carritosTotales = computed(() => this.metricas().carritos_detectados);
  readonly valorRiesgoFormateado = computed(
    () => `Bs ${(this.metricas().valor_en_riesgo || 0).toLocaleString('es-BO', { minimumFractionDigits: 2 })}`
  );
  readonly tasaRecuperacion = computed(() => `${this.metricas().tasa_conversion || 0}%`);

  ngOnInit(): void {
    this.cargarTiendas();
  }

  cargarTiendas(): void {
    this.tiendaService.listar().subscribe({
      next: (lista) => {
        this.tiendas.set(lista || []);
        if (lista && lista.length > 0) {
          this.tiendaSeleccionadaId.set(lista[0].id);
          this.cargarDatos();
        } else {
          this.cargando.set(false);
        }
      },
      error: (err) => {
        this.cargando.set(false);
        this.mensajeError.set(err?.error?.detail || 'No se pudieron cargar tus tiendas.');
      },
    });
  }

  seleccionarTienda(id: number): void {
    this.tiendaSeleccionadaId.set(id);
    this.limpiarMensajes();
    this.cargarDatos();
  }

  cargarDatos(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId) return;

    this.cargando.set(true);

    this.campanaService.obtenerCampana(tiendaId).subscribe({
      next: (resumen) => {
        if (resumen.campana) {
          this.campana.set(resumen.campana);
        }
        if (resumen.metricas) {
          this.metricas.set(resumen.metricas);
        }
        this.cargando.set(false);
      },
      error: (err) => {
        this.cargando.set(false);
        this.mensajeError.set(err?.error?.detail || 'Error al obtener la campana de carrito.');
      },
    });

    this.campanaService.listarCarritosAbandonados(tiendaId).subscribe({
      next: (carritos) => {
        this.carritosAbandonados.set(carritos || []);
      },
      error: () => {},
    });
  }

  guardarCampana(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId) return;

    this.guardando.set(true);
    this.limpiarMensajes();

    this.campanaService.guardarCampana(tiendaId, this.campana()).subscribe({
      next: (resp) => {
        this.guardando.set(false);
        if (resp.campana) {
          this.campana.set(resp.campana);
        }
        this.mensajeExito.set(resp.mensaje || 'Parametros de campana guardados correctamente.');
        this.cargarDatos();
      },
      error: (err) => {
        this.guardando.set(false);
        this.mensajeError.set(err?.error?.detail || 'No se pudo guardar la configuracion de campana.');
      },
    });
  }

  dispararPrueba(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId) return;

    this.enviandoPrueba.set(true);
    this.limpiarMensajes();

    this.campanaService.dispararPrueba(tiendaId).subscribe({
      next: (resp) => {
        this.enviandoPrueba.set(false);
        this.mensajeExito.set(resp.mensaje || 'Correo de prueba enviado con exito.');
      },
      error: (err) => {
        this.enviandoPrueba.set(false);
        this.mensajeError.set(err?.error?.detail || 'Error al enviar el correo de prueba.');
      },
    });
  }

  actualizarActivo(activo: boolean): void {
    this.campana.update((c) => ({ ...c, activo }));
  }

  actualizarHoras(horas: number): void {
    this.campana.update((c) => ({ ...c, horas_inactividad: Number(horas) || 2 }));
  }

  actualizarDescuento(descuento: number): void {
    this.campana.update((c) => ({ ...c, descuento_porcentaje: Math.max(0, Math.min(50, Number(descuento) || 0)) }));
  }

  actualizarAsunto(asunto: string): void {
    this.campana.update((c) => ({ ...c, asunto_email: asunto }));
  }

  actualizarMensaje(mensaje: string): void {
    this.campana.update((c) => ({ ...c, mensaje_email: mensaje }));
  }

  actualizarCupon(cupon: string): void {
    this.campana.update((c) => ({ ...c, codigo_cupon: cupon }));
  }

  limpiarMensajes(): void {
    this.mensajeExito.set(null);
    this.mensajeError.set(null);
  }
}
