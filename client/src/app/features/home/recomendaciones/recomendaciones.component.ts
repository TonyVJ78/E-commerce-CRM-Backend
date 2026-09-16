import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges } from '@angular/core';
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
  @Input({required: true}) tiendaId!: number;
  @Input() limit = 8;
  @Output() productoSeleccionado = new EventEmitter<ProductoCatalogo>();

  productos: ProductoCatalogo[] = [];
  cargando = false;
  error = '';
  private cargaSub?: Subscription;

  constructor(private readonly recomendacionService: RecomendacionService) {}

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
    this.error = '';
    this.productos = [];
    const tiendaSolicitada = this.tiendaId;

    this.cargaSub = this.recomendacionService.obtenerRecomendaciones(tiendaSolicitada, this.limit).subscribe({
      next: products => {
        this.productos = products.filter(product => product.tienda_id === tiendaSolicitada);
        this.cargando = false;
      },
      error: () => {
        this.error = 'No pudimos cargar tus recomendaciones en este momento.';
        this.cargando = false;
      }
    });
  }

  seleccionar(producto: ProductoCatalogo): void {
    this.recomendacionService.registrarInteraccion({
      tienda_id: this.tiendaId,
      producto_id: producto.id,
      tipo_interaccion: 'CLICK'
    }).subscribe({error: () => {}});
    this.productoSeleccionado.emit(producto);
  }

  imagen(producto: ProductoCatalogo): string {
    if (producto.imagen_principal) return producto.imagen_principal;
    const first = producto.imagenes?.[0];
    if (typeof first === 'object') return first.url;
    return first ? String(first) : '';
  }

  trackProduct(_: number, producto: ProductoCatalogo): number {
    return producto.id;
  }
}
