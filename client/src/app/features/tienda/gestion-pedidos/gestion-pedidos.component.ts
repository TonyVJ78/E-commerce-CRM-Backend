import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';
import { TiendaService } from '../../../core/services/tienda.service';
import { PedidoEmpresaService } from '../../../core/services/pedido-empresa.service';
import {
  ETIQUETA_ESTADO_PEDIDO,
  EstadoPedido,
  FLUJO_PEDIDO,
  PedidoRecibido,
  PedidoRecibidoDetalle,
  Tienda,
} from '../../../core/models';

type FiltroEstado = EstadoPedido | '';

const ACCION_AVANZAR: Partial<Record<EstadoPedido, string>> = {
  procesado: 'Marcar como procesado',
  enviado: 'Marcar como enviado',
  entregado: 'Confirmar entrega',
};

/** CU-22 — Gestionar pedidos recibidos: la empresa avanza el estado de los pedidos de su tienda. */
@Component({
  selector: 'app-gestion-pedidos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './gestion-pedidos.component.html',
  styleUrls: ['./gestion-pedidos.component.css'],
})
export class GestionPedidosComponent implements OnInit, OnDestroy {
  private readonly tiendaService = inject(TiendaService);
  private readonly pedidoService = inject(PedidoEmpresaService);

  readonly flujo = FLUJO_PEDIDO;
  readonly etiquetas = ETIQUETA_ESTADO_PEDIDO;
  readonly pestanas: { valor: FiltroEstado; etiqueta: string }[] = [
    { valor: '', etiqueta: 'Todos' },
    ...FLUJO_PEDIDO.map(e => ({ valor: e as FiltroEstado, etiqueta: ETIQUETA_ESTADO_PEDIDO[e] })),
    { valor: 'cancelado', etiqueta: 'Cancelados' },
  ];

  tiendas: Tienda[] = [];
  tiendaSeleccionadaId: number | null = null;

  pedidos: PedidoRecibido[] = [];
  conteos: Partial<Record<EstadoPedido, number>> = {};
  totalPedidos = 0;
  filtroEstado: FiltroEstado = '';
  busqueda = '';

  cargando = false;
  mensajeExito = '';
  mensajeError = '';

  detalle: PedidoRecibidoDetalle | null = null;
  cargandoDetalle = false;
  actualizando = false;
  confirmandoCancelacion = false;
  transportista = '';
  numeroSeguimiento = '';

  private readonly busqueda$ = new Subject<string>();
  private readonly subs = new Subscription();

  ngOnInit(): void {
    this.subs.add(
      this.busqueda$.pipe(debounceTime(300), distinctUntilChanged()).subscribe(() => this.cargarPedidos())
    );

    this.cargando = true;
    this.tiendaService.listar().subscribe({
      next: tiendas => {
        this.tiendas = tiendas;
        if (tiendas.length > 0) {
          this.tiendaSeleccionadaId = tiendas[0].id;
          this.cargarPedidos();
        } else {
          this.cargando = false;
        }
      },
      error: () => {
        this.mensajeError = 'No se pudieron cargar tus tiendas.';
        this.cargando = false;
      },
    });
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  cambiarTienda(tiendaId: string | number): void {
    this.tiendaSeleccionadaId = Number(tiendaId);
    this.cerrarDetalle();
    this.cargarPedidos();
  }

  cambiarFiltro(estado: FiltroEstado): void {
    if (this.filtroEstado === estado) {
      return;
    }
    this.filtroEstado = estado;
    this.cargarPedidos();
  }

  onBusqueda(texto: string): void {
    this.busqueda$.next(texto);
  }

  conteoPestana(valor: FiltroEstado): number {
    return valor ? this.conteos[valor] ?? 0 : this.totalPedidos;
  }

  cargarPedidos(): void {
    if (!this.tiendaSeleccionadaId) {
      return;
    }
    this.cargando = true;
    this.pedidoService
      .listar(this.tiendaSeleccionadaId, { estado: this.filtroEstado, q: this.busqueda })
      .subscribe({
        next: resp => {
          this.pedidos = resp.pedidos;
          this.conteos = resp.conteos;
          this.totalPedidos = resp.total;
          this.cargando = false;
        },
        error: err => {
          this.mensajeError = this.extraerError(err, 'No se pudieron cargar los pedidos.');
          this.pedidos = [];
          this.cargando = false;
        },
      });
  }

  abrirDetalle(pedido: PedidoRecibido): void {
    if (!this.tiendaSeleccionadaId) {
      return;
    }
    this.cargandoDetalle = true;
    this.confirmandoCancelacion = false;
    this.transportista = '';
    this.numeroSeguimiento = '';
    this.detalle = null;
    this.pedidoService.detalle(this.tiendaSeleccionadaId, pedido.id).subscribe({
      next: det => {
        this.detalle = det;
        this.transportista = det.envio?.transportista ?? '';
        this.numeroSeguimiento = det.envio?.numero_seguimiento ?? '';
        this.cargandoDetalle = false;
      },
      error: err => {
        this.mensajeError = this.extraerError(err, 'No se pudo cargar el detalle del pedido.');
        this.cargandoDetalle = false;
      },
    });
  }

  cerrarDetalle(): void {
    this.detalle = null;
    this.cargandoDetalle = false;
    this.confirmandoCancelacion = false;
  }

  siguienteEstado(det: PedidoRecibidoDetalle): EstadoPedido | null {
    return det.siguientes_estados.find(e => e !== 'cancelado') ?? null;
  }

  textoAvanzar(estado: EstadoPedido): string {
    return ACCION_AVANZAR[estado] ?? `Pasar a ${this.etiquetas[estado]}`;
  }

  puedeCancelar(det: PedidoRecibidoDetalle): boolean {
    return det.siguientes_estados.includes('cancelado');
  }

  estadoPaso(det: PedidoRecibidoDetalle, paso: EstadoPedido): 'hecho' | 'actual' | 'pendiente' {
    if (det.estado === 'cancelado') {
      return det.historial.some(h => h.estado === paso) ? 'hecho' : 'pendiente';
    }
    const diferencia = FLUJO_PEDIDO.indexOf(paso) - FLUJO_PEDIDO.indexOf(det.estado);
    return diferencia < 0 ? 'hecho' : diferencia === 0 ? 'actual' : 'pendiente';
  }

  fechaPaso(det: PedidoRecibidoDetalle, paso: EstadoPedido): string | null {
    const registros = det.historial.filter(h => h.estado === paso);
    return registros.length ? registros[registros.length - 1].fecha : null;
  }

  cambiarEstado(estado: EstadoPedido): void {
    if (!this.detalle || !this.tiendaSeleccionadaId || this.actualizando) {
      return;
    }
    this.actualizando = true;
    this.limpiarMensajes();

    const payload = estado === 'enviado'
      ? { estado, transportista: this.transportista, numero_seguimiento: this.numeroSeguimiento }
      : { estado };

    this.pedidoService.cambiarEstado(this.tiendaSeleccionadaId, this.detalle.id, payload).subscribe({
      next: det => {
        this.detalle = det;
        this.confirmandoCancelacion = false;
        this.mensajeExito = [det.mensaje ?? 'Pedido actualizado.', det.aviso].filter(Boolean).join(' ');
        this.actualizando = false;
        this.cargarPedidos();
      },
      error: err => {
        this.mensajeError = this.extraerError(err, 'No se pudo actualizar el estado del pedido.');
        this.actualizando = false;
        // 409: el pedido cambió por otro lado; se recarga para mostrar su estado real.
        if (err?.status === 409 && this.detalle) {
          this.abrirDetalle(this.detalle);
          this.cargarPedidos();
        }
      },
    });
  }

  private limpiarMensajes(): void {
    this.mensajeExito = '';
    this.mensajeError = '';
  }

  private extraerError(err: any, porDefecto: string): string {
    return err?.error?.error || err?.error?.detail || porDefecto;
  }
}
