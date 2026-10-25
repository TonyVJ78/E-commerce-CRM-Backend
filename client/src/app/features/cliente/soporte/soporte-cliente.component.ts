import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SoporteService } from '../../../core/services/soporte.service';
import {
  PedidoCliente,
  PedidosClienteService,
} from '../../../core/services/pedidos-cliente.service';
import { TiendaService } from '../../../core/services/tienda.service';
import {
  TicketSoporte,
  MensajeTicket,
  CrearTicketRequest,
} from '../../../core/models/soporte.model';
import { Tienda } from '../../../core/models';

@Component({
  selector: 'app-soporte-cliente',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule, RouterLink],
  templateUrl: './soporte-cliente.component.html',
  styleUrl: './soporte-cliente.component.scss',
})
export class SoporteClienteComponent implements OnInit {
  private readonly soporteService = inject(SoporteService);
  private readonly pedidosService = inject(PedidosClienteService);
  private readonly tiendaService = inject(TiendaService);
  private readonly route = inject(ActivatedRoute);

  // Estados reactivos (Signals)
  readonly tickets = signal<TicketSoporte[]>([]);
  readonly ticketSeleccionado = signal<TicketSoporte | null>(null);
  readonly pedidos = signal<PedidoCliente[]>([]);
  readonly tiendas = signal<Tienda[]>([]);

  readonly cargandoTickets = signal<boolean>(true);
  readonly cargandoDetalle = signal<boolean>(false);
  readonly enviandoRespuesta = signal<boolean>(false);
  readonly guardandoTicket = signal<boolean>(false);

  readonly modalNuevoAbierto = signal<boolean>(false);
  readonly mensajeExito = signal<string | null>(null);
  readonly mensajeError = signal<string | null>(null);

  // Formulario nuevo ticket
  nuevoTicket: CrearTicketRequest = {
    tipo: 'consulta',
    prioridad: 'media',
    asunto: '',
    descripcion: '',
    tienda_id: null,
    pedido_id: null,
    archivo_adjunto: '',
  };

  // Campo de respuesta en chat
  textoRespuesta = signal<string>('');

  // Senales computadas
  readonly totalTickets = computed(() => this.tickets().length);
  readonly ticketsAbiertos = computed(
    () => this.tickets().filter((t) => t.estado === 'abierto' || t.estado === 'en_proceso').length
  );
  readonly ticketsResueltos = computed(
    () => this.tickets().filter((t) => t.estado === 'resuelto' || t.estado === 'cerrado').length
  );

  ngOnInit(): void {
    this.cargarMisTickets();
    this.cargarContextoCliente();

    // Si viene parametro query pedido_id, preparar el modal
    this.route.queryParams.subscribe((params) => {
      const pedidoId = params['pedido_id'];
      if (pedidoId) {
        this.nuevoTicket.pedido_id = Number(pedidoId);
        this.abrirModalNuevoTicket();
      }
    });
  }

  cargarMisTickets(): void {
    this.cargandoTickets.set(true);
    this.soporteService.listarMisTickets().subscribe({
      next: (data) => {
        this.tickets.set(data);
        this.cargandoTickets.set(false);
        // Si hay ticket seleccionado, refrescarlo
        const actual = this.ticketSeleccionado();
        if (actual) {
          const refrescado = data.find((t) => t.id === actual.id);
          if (refrescado) {
            this.seleccionarTicket(refrescado);
          }
        }
      },
      error: (err) => {
        this.cargandoTickets.set(false);
        this.mensajeError.set(err?.error?.detail || 'No se pudieron cargar tus tickets de soporte.');
      },
    });
  }

  cargarContextoCliente(): void {
    this.pedidosService.listar().subscribe({
      next: (resp) => this.pedidos.set(resp?.pedidos || []),
      error: () => {},
    });

    this.tiendaService.listar().subscribe({
      next: (tiendas) => this.tiendas.set(tiendas || []),
      error: () => {},
    });
  }

  seleccionarTicket(ticket: TicketSoporte): void {
    this.cargandoDetalle.set(true);
    this.soporteService.obtenerDetalle(ticket.id).subscribe({
      next: (detalle) => {
        this.ticketSeleccionado.set(detalle);
        this.cargandoDetalle.set(false);
      },
      error: () => {
        this.ticketSeleccionado.set(ticket);
        this.cargandoDetalle.set(false);
      },
    });
  }

  abrirModalNuevoTicket(): void {
    this.limpiarMensajes();
    this.modalNuevoAbierto.set(true);
  }

  cerrarModalNuevoTicket(): void {
    this.modalNuevoAbierto.set(false);
    this.nuevoTicket = {
      tipo: 'consulta',
      prioridad: 'media',
      asunto: '',
      descripcion: '',
      tienda_id: null,
      pedido_id: null,
      archivo_adjunto: '',
    };
  }

  crearTicket(): void {
    if (!this.nuevoTicket.asunto.trim() || !this.nuevoTicket.descripcion.trim()) {
      this.mensajeError.set('Por favor completa el asunto y la descripcion del problema.');
      return;
    }

    if (!this.nuevoTicket.pedido_id && !this.nuevoTicket.tienda_id) {
      this.mensajeError.set('Selecciona un pedido asociado o una tienda.');
      return;
    }

    this.guardandoTicket.set(true);
    this.limpiarMensajes();

    this.soporteService.crearTicket(this.nuevoTicket).subscribe({
      next: (creado) => {
        this.guardandoTicket.set(false);
        this.mensajeExito.set(`Ticket ${creado.codigo_ticket} registrado con exito.`);
        this.cerrarModalNuevoTicket();
        this.cargarMisTickets();
        this.seleccionarTicket(creado);
      },
      error: (err) => {
        this.guardandoTicket.set(false);
        this.mensajeError.set(err?.error?.detail || 'Error al registrar el ticket de soporte.');
      },
    });
  }

  enviarRespuesta(): void {
    const ticket = this.ticketSeleccionado();
    const texto = this.textoRespuesta().trim();

    if (!ticket || !texto) {
      return;
    }

    this.enviandoRespuesta.set(true);
    this.soporteService.responderTicket(ticket.id, texto).subscribe({
      next: (nuevoMensaje) => {
        this.enviandoRespuesta.set(false);
        this.textoRespuesta.set('');
        // Anexar mensaje reactivamente
        const actual = this.ticketSeleccionado();
        if (actual) {
          const mensajesActualizados = [...(actual.mensajes || []), nuevoMensaje];
          this.ticketSeleccionado.set({ ...actual, mensajes: mensajesActualizados });
        }
      },
      error: (err) => {
        this.enviandoRespuesta.set(false);
        this.mensajeError.set(err?.error?.detail || 'No se pudo enviar la respuesta.');
      },
    });
  }

  claseBadgeEstado(estado: string): string {
    switch (estado) {
      case 'abierto':
        return 'badge--danger';
      case 'en_proceso':
        return 'badge--warning';
      case 'resuelto':
      case 'cerrado':
        return 'badge--success';
      default:
        return 'badge--neutral';
    }
  }

  claseBadgePrioridad(prioridad: string): string {
    switch (prioridad) {
      case 'urgente':
        return 'badge--danger';
      case 'alta':
        return 'badge--warning';
      case 'media':
        return 'badge--neutral';
      case 'baja':
        return 'badge--neutral';
      default:
        return 'badge--neutral';
    }
  }

  limpiarMensajes(): void {
    this.mensajeExito.set(null);
    this.mensajeError.set(null);
  }
}
