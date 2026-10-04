import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import {
  PedidoCliente,
  PedidosClienteService,
} from '../../../core/services/pedidos-cliente.service';

@Component({
  selector: 'app-pedidos-cliente',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule],
  templateUrl: './pedidos.component.html',
  styleUrls: ['./pedidos.component.css'],
})
export class PedidosClienteComponent implements OnInit {
  private readonly pedidosService = inject(PedidosClienteService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  pedidos: PedidoCliente[] = [];
  seleccionado: PedidoCliente | null = null;
  cargando = true;
  cargandoDetalle = false;
  guardandoResena = false;
  error = '';
  mensaje = '';
  hoverCalificacion = 0;

  readonly resenaForm = this.fb.group({
    tipo: this.fb.control<'producto' | 'tienda'>('producto', {
      nonNullable: true,
      validators: [Validators.required],
    }),
    producto_id: this.fb.control<number | null>(null),
    calificacion: this.fb.control<number>(5, {
      nonNullable: true,
      validators: [Validators.required, Validators.min(1), Validators.max(5)],
    }),
    comentario: this.fb.control<string>('', {
      nonNullable: true,
      validators: [Validators.maxLength(5000)],
    }),
  });

  ngOnInit(): void {
    this.escucharCambiosTipoResena();
    this.cargarPedidos();
  }

  private escucharCambiosTipoResena(): void {
    this.resenaForm.get('tipo')?.valueChanges.subscribe((tipo) => {
      const productoIdControl = this.resenaForm.get('producto_id');
      if (tipo === 'producto') {
        productoIdControl?.setValidators([Validators.required]);
        if (this.seleccionado?.items.length && !productoIdControl?.value) {
          const primerValido = this.seleccionado.items.find((i) => i.producto_id)?.producto_id ?? null;
          productoIdControl?.setValue(primerValido);
        }
      } else {
        productoIdControl?.clearValidators();
        productoIdControl?.setValue(null);
      }
      productoIdControl?.updateValueAndValidity();
    });
  }

  cargarPedidos(): void {
    this.cargando = true;
    this.error = '';
    this.pedidosService.listar().subscribe({
      next: (response) => {
        this.pedidos = response.pedidos;
        this.cargando = false;

        // Comprobar si vino con query param ?id=X
        const paramId = this.route.snapshot.queryParamMap.get('id');
        if (paramId && !isNaN(Number(paramId))) {
          this.abrirPedido(Number(paramId), false);
        } else if (this.seleccionado) {
          this.abrirPedido(this.seleccionado.id, false);
        } else if (this.pedidos.length > 0) {
          // Abrir el primer pedido automáticamente para desktop
          this.abrirPedido(this.pedidos[0].id, true);
        }
      },
      error: () => {
        this.error = 'No se pudieron cargar tus pedidos. Por favor, intenta nuevamente.';
        this.cargando = false;
      },
    });
  }

  abrirPedido(id: number, actualizarUrl = true): void {
    this.cargandoDetalle = true;
    this.error = '';
    this.mensaje = '';

    this.pedidosService.obtener(id).subscribe({
      next: (pedido) => {
        this.seleccionado = pedido;
        this.cargandoDetalle = false;
        this.actualizarFormularioParaPedido(pedido);

        if (actualizarUrl) {
          this.router.navigate([], {
            relativeTo: this.route,
            queryParams: { id: pedido.id },
            queryParamsHandling: 'merge',
          });
        }
      },
      error: (response) => {
        this.seleccionado = null;
        this.cargandoDetalle = false;
        this.error =
          response.status === 404
            ? 'El pedido solicitado no fue encontrado o no pertenece a tu cuenta.'
            : 'No se pudo cargar el detalle del pedido.';

        // Redirigir limpiamente a /pedidos eliminando query params inválidos (Regla de aislamiento multitenant)
        this.router.navigate(['/pedidos'], { replaceUrl: true });
      },
    });
  }

  private actualizarFormularioParaPedido(pedido: PedidoCliente): void {
    const primerProductoId = pedido.items.find((item) => item.producto_id)?.producto_id ?? null;
    this.resenaForm.reset({
      tipo: 'producto',
      producto_id: primerProductoId,
      calificacion: 5,
      comentario: '',
    });
  }

  puedeCalificar(pedido: PedidoCliente): boolean {
    const estadosPermitidos = ['completado', 'completada', 'entregado', 'finalizado', 'completed'];
    return estadosPermitidos.includes((pedido.estado || '').trim().toLowerCase());
  }

  setCalificacion(estrellas: number): void {
    this.resenaForm.patchValue({ calificacion: estrellas });
  }

  guardarResena(): void {
    if (!this.seleccionado || this.guardandoResena || !this.puedeCalificar(this.seleccionado)) {
      return;
    }

    if (this.resenaForm.invalid) {
      this.resenaForm.markAllAsTouched();
      return;
    }

    const { tipo, producto_id, calificacion, comentario } = this.resenaForm.getRawValue();

    if (tipo === 'producto' && !producto_id) {
      this.error = 'Debes seleccionar un producto válido de este pedido para calificarlo.';
      return;
    }

    this.guardandoResena = true;
    this.error = '';
    this.mensaje = '';

    this.pedidosService
      .guardarResena(this.seleccionado.id, {
        tipo,
        ...(tipo === 'producto' && producto_id ? { producto_id } : {}),
        calificacion,
        comentario: comentario.trim(),
      })
      .subscribe({
        next: () => {
          this.guardandoResena = false;
          this.mensaje = '¡Tu calificación fue registrada exitosamente!';
          this.resenaForm.patchValue({ comentario: '' });
          // Recargar el detalle del pedido para visualizar la reseña inmediatamente
          this.abrirPedido(this.seleccionado!.id, false);
        },
        error: (response) => {
          this.guardandoResena = false;
          this.error =
            response.error?.error || 'No se pudo guardar la calificación. Intenta de nuevo.';
        },
      });
  }

  etiquetaEstado(estado: string): string {
    const mapa: Record<string, string> = {
      pendiente: 'Pendiente',
      en_preparacion: 'En Preparación',
      enviado: 'En Camino',
      entregado: 'Entregado',
      completado: 'Completado',
      cancelado: 'Cancelado',
    };
    return mapa[(estado || '').toLowerCase()] || (estado || '').replace(/_/g, ' ');
  }

  claseBadgeEstado(estado: string): string {
    const s = (estado || '').toLowerCase();
    if (s === 'entregado' || s === 'completado') return 'badge-entregado';
    if (s === 'en_preparacion') return 'badge-preparacion';
    if (s === 'enviado') return 'badge-enviado';
    if (s === 'pendiente') return 'badge-pendiente';
    if (s === 'cancelado') return 'badge-cancelado';
    return 'badge-default';
  }

  iconoEstado(estado: string): string {
    const s = (estado || '').toLowerCase();
    if (s === 'entregado' || s === 'completado') return '✨';
    if (s === 'en_preparacion') return '📦';
    if (s === 'enviado') return '🚚';
    if (s === 'pendiente') return '⏳';
    if (s === 'cancelado') return '⚠️';
    return '📋';
  }
}
