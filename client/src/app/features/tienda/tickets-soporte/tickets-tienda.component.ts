import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SoporteService } from '../../../core/services/soporte.service';
import { TiendaService } from '../../../core/services/tienda.service';
import {
  TicketSoporte,
  KpisTicketsTienda,
} from '../../../core/models/soporte.model';
import { Tienda } from '../../../core/models';

@Component({
  selector: 'app-tickets-tienda',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule, RouterLink],
  templateUrl: './tickets-tienda.component.html',
  styleUrl: './tickets-tienda.component.scss',
})
export class TicketsTiendaComponent implements OnInit {
  private readonly soporteService = inject(SoporteService);
  private readonly tiendaService = inject(TiendaService);

  readonly tiendas = signal<Tienda[]>([]);
  readonly tiendaSeleccionadaId = signal<number | null>(null);

  readonly tickets = signal<TicketSoporte[]>([]);
  readonly kpis = signal<KpisTicketsTienda>({
    total_abiertos: 0,
    total_en_proceso: 0,
    total_resueltos: 0,
    total_tickets: 0,
  });

  readonly cargando = signal<boolean>(true);
  readonly ticketSeleccionado = signal<TicketSoporte | null>(null);
  readonly drawerAbierto = signal<boolean>(false);
  readonly enviandoMensaje = signal<boolean>(false);
  readonly actualizandoEstado = signal<boolean>(false);

  readonly filtroEstado = signal<string>('');
  readonly filtroPrioridad = signal<string>('');
  readonly textoRespuesta = signal<string>('');

  readonly mensajeExito = signal<string | null>(null);
  readonly mensajeError = signal<string | null>(null);

  ngOnInit(): void {
    this.cargarTiendas();
  }

  cargarTiendas(): void {
    this.tiendaService.listar().subscribe({
      next: (lista) => {
        this.tiendas.set(lista || []);
        if (lista && lista.length > 0) {
          this.tiendaSeleccionadaId.set(lista[0].id);
          this.cargarTickets();
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
    this.cerrarDrawer();
    this.cargarTickets();
  }

  cargarTickets(): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId) return;

    this.cargando.set(true);
    this.soporteService
      .listarPorTienda(tiendaId, {
        estado: this.filtroEstado(),
        prioridad: this.filtroPrioridad(),
      })
      .subscribe({
        next: (resp) => {
          this.tickets.set(resp.tickets || []);
          this.kpis.set(resp.kpis || {
            total_abiertos: 0,
            total_en_proceso: 0,
            total_resueltos: 0,
            total_tickets: 0,
          });
          this.cargando.set(false);
        },
        error: (err) => {
          this.cargando.set(false);
          this.mensajeError.set(err?.error?.detail || 'Error al obtener tickets de la tienda.');
        },
      });
  }

  cambiarEstado(ticket: TicketSoporte, nuevoEstado: string): void {
    const tiendaId = this.tiendaSeleccionadaId();
    if (!tiendaId || ticket.estado === nuevoEstado) return;

    this.actualizandoEstado.set(true);
    this.soporteService.actualizarEstado(tiendaId, ticket.id, nuevoEstado).subscribe({
      next: (actualizado) => {
        this.actualizandoEstado.set(false);
        this.mensajeExito.set(`Ticket ${ticket.codigo_ticket} actualizado a estado '${actualizado.estado_display}'.`);
        // Actualizar en la lista reactivamente
        this.tickets.update((prev) =>
          prev.map((t) => (t.id === ticket.id ? { ...t, ...actualizado } : t))
        );
        if (this.ticketSeleccionado()?.id === ticket.id) {
          this.ticketSeleccionado.update((t) => (t ? { ...t, ...actualizado } : null));
        }
        // Recalcular KPIs recargando datos
        this.cargarTickets();
      },
      error: (err) => {
        this.actualizandoEstado.set(false);
        this.mensajeError.set(err?.error?.detail || 'No se pudo actualizar el estado.');
      },
    });
  }

  abrirDrawer(ticket: TicketSoporte): void {
    this.soporteService.obtenerDetalle(ticket.id).subscribe({
      next: (detalle) => {
        this.ticketSeleccionado.set(detalle);
        this.drawerAbierto.set(true);
      },
      error: () => {
        this.ticketSeleccionado.set(ticket);
        this.drawerAbierto.set(true);
      },
    });
  }

  cerrarDrawer(): void {
    this.drawerAbierto.set(false);
    this.ticketSeleccionado.set(null);
    this.textoRespuesta.set('');
  }

  enviarRespuesta(): void {
    const ticket = this.ticketSeleccionado();
    const texto = this.textoRespuesta().trim();

    if (!ticket || !texto) return;

    this.enviandoMensaje.set(true);
    this.soporteService.responderTicket(ticket.id, texto).subscribe({
      next: (nuevoMensaje) => {
        this.enviandoMensaje.set(false);
        this.textoRespuesta.set('');
        // Anexar mensaje
        this.ticketSeleccionado.update((actual) => {
          if (!actual) return null;
          return {
            ...actual,
            estado: actual.estado === 'abierto' ? 'en_proceso' : actual.estado,
            estado_display: actual.estado === 'abierto' ? 'En Proceso' : actual.estado_display,
            mensajes: [...(actual.mensajes || []), nuevoMensaje],
          };
        });
        // Actualizar en tabla
        this.cargarTickets();
      },
      error: (err) => {
        this.enviandoMensaje.set(false);
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
