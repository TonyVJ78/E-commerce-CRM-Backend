import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges, inject } from '@angular/core';
import { Subscription } from 'rxjs';

import { ProductoCatalogo } from '../../../core/models/catalogo.model';
import { RecomendacionService } from '../../../core/services/recomendacion.service';

@Component({
  selector: 'app-recomendaciones',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './recomendaciones.component.html',
  styleUrls: ['./recomendaciones.component.css']
})
export class RecomendacionesComponent implements OnChanges, OnDestroy {
  private readonly recomendacionService = inject(RecomendacionService);

  @Input({ required: true }) tiendaId!: number;
  @Input() limit = 8;
  @Output() productoSeleccionado = new EventEmitter<ProductoCatalogo>();

  productos: ProductoCatalogo[] = [];
  cargando = false;
  private cargaSub?: Subscription;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['tiendaId'] && this.tiendaId > 0) {
      this.cargar();
    }
  }

  ngOnDestroy(): void {
    this.cargaSub?.unsubscribe();
  }

  cargar(): void {
    this.cargaSub?.unsubscribe();
    this.cargando = true;
    this.productos = [];
    const tiendaSolicitada = this.tiendaId;

    this.cargaSub = this.recomendacionService
      .obtenerRecomendaciones(tiendaSolicitada, this.limit)
      .subscribe({
        next: products => {
          // Filtrar por la tienda solicitada
          this.productos = (products || []).filter(p => p.tienda_id === tiendaSolicitada);
          this.cargando = false;
        },
        error: () => {
          // Resiliencia silenciosa: en caso de error se oculta el widget sin lanzar errores en consola
          this.productos = [];
          this.cargando = false;
        }
      });
  }

  /**
   * Disparo fire-and-forget al endpoint de telemetría (/api/ia/eventos/).
   * No bloquea la navegación del usuario ni la apertura del detalle.
   */
  seleccionar(producto: ProductoCatalogo): void {
    this.recomendacionService.notificarInteraccion({
      tienda_id: this.tiendaId,
      producto_id: producto.id,
      tipo_interaccion: 'CLICK'
    });
    this.productoSeleccionado.emit(producto);
  }

  imagen(producto: ProductoCatalogo): string {
    if (producto.imagen_principal) return producto.imagen_principal;
    const first = producto.imagenes?.[0];
    if (typeof first === 'object') return (first as any).url;
    return first ? String(first) : '';
  }

  trackProduct(_: number, producto: ProductoCatalogo): number {
    return producto.id;
  }
}
