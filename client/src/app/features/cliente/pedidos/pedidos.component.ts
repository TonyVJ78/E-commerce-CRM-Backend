import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PedidoCliente, PedidosClienteService } from '../../../core/services/pedidos-cliente.service';

@Component({
  selector: 'app-pedidos-cliente',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pedidos.component.html',
  styleUrls: ['./pedidos.component.css']
})
export class PedidosClienteComponent implements OnInit {
  pedidos: PedidoCliente[] = [];
  seleccionado: PedidoCliente | null = null;
  cargando = true;
  guardandoResena = false;
  error = '';
  mensaje = '';
  tipoResena: 'producto' | 'tienda' = 'producto';
  productoId: number | null = null;
  calificacion = 5;
  comentario = '';

  constructor(private readonly pedidosService: PedidosClienteService) {}

  ngOnInit(): void {
    this.cargarPedidos();
  }

  cargarPedidos(): void {
    this.cargando = true;
    this.pedidosService.listar().subscribe({
      next: response => {
        this.pedidos = response.pedidos;
        this.cargando = false;
        if (this.seleccionado) this.abrirPedido(this.seleccionado.id);
      },
      error: () => {
        this.error = 'No se pudieron cargar tus pedidos.';
        this.cargando = false;
      }
    });
  }

  abrirPedido(id: number): void {
    this.error = '';
    this.mensaje = '';
    this.pedidosService.obtener(id).subscribe({
      next: pedido => {
        this.seleccionado = pedido;
        this.productoId = pedido.items.find(item => item.producto_id)?.producto_id ?? null;
      },
      error: response => {
        this.seleccionado = null;
        this.error = response.status === 404
          ? 'No se encontró el pedido solicitado.'
          : 'No se pudo cargar el seguimiento del pedido.';
      }
    });
  }

  puedeCalificar(pedido: PedidoCliente): boolean {
    return ['completado', 'completada', 'entregado', 'finalizado', 'completed']
      .includes(pedido.estado.trim().toLowerCase());
  }

  guardarResena(): void {
    if (!this.seleccionado || this.guardandoResena) return;
    if (this.tipoResena === 'producto' && !this.productoId) {
      this.error = 'Selecciona un producto de este pedido.';
      return;
    }
    this.guardandoResena = true;
    this.error = '';
    this.mensaje = '';
    this.pedidosService.guardarResena(this.seleccionado.id, {
      tipo: this.tipoResena,
      ...(this.tipoResena === 'producto' ? { producto_id: this.productoId ?? undefined } : {}),
      calificacion: this.calificacion,
      comentario: this.comentario.trim()
    }).subscribe({
      next: () => {
        this.guardandoResena = false;
        this.mensaje = 'Tu calificación quedó registrada.';
        this.comentario = '';
        this.abrirPedido(this.seleccionado!.id);
      },
      error: response => {
        this.guardandoResena = false;
        this.error = response.error?.error ?? 'No se pudo registrar la calificación.';
      }
    });
  }

  etiquetaEstado(estado: string): string {
    return estado.replaceAll('_', ' ');
  }
}