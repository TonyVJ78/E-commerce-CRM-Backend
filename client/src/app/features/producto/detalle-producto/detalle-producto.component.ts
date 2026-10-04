import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, catchError, of, switchMap } from 'rxjs';
import { ProductoCatalogo, VarianteCatalogo } from '../../../core/models';
import { CarritoService } from '../../../core/services/carrito.service';
import { CatalogoService } from '../../../core/services/catalogo.service';

const IMAGEN_RESPALDO =
  'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=900&q=80';

/**
 * Ficha de un producto del catálogo público.
 *
 * Es el destino de las recomendaciones del chatbot, y al tener URL propia
 * (`/producto/:id`) se puede abrir en otra pestaña o compartir.
 */
@Component({
  selector: 'app-detalle-producto',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './detalle-producto.component.html',
  styleUrls: ['./detalle-producto.component.css']
})
export class DetalleProductoComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly catalogoService = inject(CatalogoService);
  private readonly carritoService = inject(CarritoService);

  producto: ProductoCatalogo | null = null;
  variante: VarianteCatalogo | null = null;
  imagenActiva = '';
  cargando = true;
  noEncontrado = false;
  agregando = false;
  mensajeExito = '';
  mensajeError = '';

  private readonly subs = new Subscription();

  ngOnInit(): void {
    // El chat puede abrir otro producto estando ya en esta ruta: se escucha el
    // parámetro en vez de leerlo una sola vez. El error se atrapa dentro del
    // switchMap; si llegara al subscribe, cortaría la escucha del parámetro.
    this.subs.add(
      this.route.paramMap.pipe(
        switchMap(params => {
          this.cargando = true;
          this.limpiarMensajes();
          return this.catalogoService.obtenerProducto(Number(params.get('id'))).pipe(
            catchError(() => of(null))
          );
        })
      ).subscribe(producto => {
        this.producto = producto;
        this.noEncontrado = !producto;
        this.variante = producto
          ? producto.variantes.find(v => v.stock > 0) ?? producto.variantes[0] ?? null
          : null;
        this.imagenActiva = this.imagenes[0];
        this.cargando = false;
        window.scrollTo({ top: 0 });
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  get imagenes(): string[] {
    const urls = (this.producto?.imagenes || [])
      .map(img => (typeof img === 'object' ? img.url : String(img)))
      .filter(Boolean);
    return urls.length ? urls : [this.producto?.imagen_principal || IMAGEN_RESPALDO];
  }

  get precioActual(): string {
    const v = this.variante;
    return v ? (v.precio_oferta ?? v.precio) : (this.producto?.precio_base || '0.00');
  }

  get precioAnterior(): string | null {
    const v = this.variante;
    return v?.precio_oferta ? v.precio : null;
  }

  get atributos(): Array<[string, string]> {
    return Object.entries(this.variante?.atributos || {});
  }

  seleccionarVariante(variante: VarianteCatalogo): void {
    this.variante = variante;
  }

  agregarAlCarrito(): void {
    const producto = this.producto;
    const variante = this.variante;
    if (!producto?.tienda_id || !variante || variante.stock <= 0) return;

    this.limpiarMensajes();
    this.agregando = true;
    this.carritoService.agregarItem({ tienda_id: producto.tienda_id, variante_id: variante.id }).subscribe({
      next: () => {
        this.agregando = false;
        this.mensajeExito = `¡Agregado al carrito! ${producto.nombre} (${variante.nombre})`;
        setTimeout(() => this.limpiarMensajes(), 4000);
      },
      error: (error: HttpErrorResponse) => {
        this.agregando = false;
        const resp = error.error;
        this.mensajeError = resp?.detail || (typeof resp === 'string' && resp) ||
          'No se pudo agregar el producto al carrito.';
      }
    });
  }

  private limpiarMensajes(): void {
    this.mensajeExito = '';
    this.mensajeError = '';
  }
}
