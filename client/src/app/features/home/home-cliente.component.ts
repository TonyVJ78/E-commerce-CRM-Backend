import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import {
  ProductoCatalogo,
  TiendaCatalogo,
  VarianteCatalogo,
  CategoriaCatalogo
} from '../../core/models';
import { CatalogoService } from '../../core/services/catalogo.service';
import { CarritoService } from '../../core/services/carrito.service';

@Component({
  selector: 'app-home-cliente',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './home-cliente.component.html',
  styleUrls: ['./home-cliente.component.css']
})
export class HomeClienteComponent implements OnInit, OnDestroy {
  productos: ProductoCatalogo[] = [];
  categorias: CategoriaCatalogo[] = [];
  tiendas: TiendaCatalogo[] = [];

  // Filtros activos
  categoriaSeleccionadaId: number | null = null;
  tiendaSeleccionadaId: number | null = null;
  terminoBusqueda = '';

  // Estados de carga
  cargando = false;
  agregandoVarianteId: number | null = null;
  varianteSeleccionadaPorProducto: { [productoId: number]: VarianteCatalogo } = {};

  // Notificaciones
  mensajeExito = '';
  mensajeError = '';

  private readonly subs = new Subscription();

  constructor(
    private readonly catalogoService: CatalogoService,
    private readonly carritoService: CarritoService
  ) {}

  ngOnInit(): void {
    this.cargarFiltrosYCatalogoGeneral();

    // Escuchar cuando el usuario hace checkout en el carrito
    this.subs.add(
      this.carritoService.checkoutCompleted$.subscribe((res) => {
        // 1. Decremento optimista inmediato en la interfaz
        if (res?.items_comprados && res.items_comprados.length > 0) {
          for (const item of res.items_comprados) {
            for (const prod of this.productos) {
              if (prod.variantes) {
                for (const v of prod.variantes) {
                  if (v.id === item.variante_id) {
                    v.stock = Math.max(0, v.stock - item.cantidad);
                  }
                }
              }
            }
          }
        }

        // 2. Banner de confirmación en la vista
        this.mensajeExito = '¡Compra realizada con éxito! El inventario ha sido actualizado en tiempo real.';
        setTimeout(() => this.limpiarMensajes(), 5000);

        // 3. Re-sincronizar catálogo con el backend
        this.recargarCatalogoSilencioso();
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  cargarFiltrosYCatalogoGeneral(): void {
    this.cargando = true;
    this.limpiarMensajes();

    // 1. Cargar categorías disponibles
    this.catalogoService.listarCategorias().subscribe({
      next: (cats) => {
        this.categorias = cats;
      },
      error: () => {}
    });

    // 2. Cargar tiendas disponibles
    this.catalogoService.listarTiendas().subscribe({
      next: (tiendas) => {
        this.tiendas = tiendas;
      },
      error: () => {}
    });

    // 3. Cargar todos los productos en general al inicio
    this.aplicarFiltros();
  }

  aplicarFiltros(): void {
    this.cargando = true;
    this.limpiarMensajes();

    const filtros: { categoria?: number; tienda?: number; q?: string } = {};
    if (this.categoriaSeleccionadaId) {
      filtros.categoria = this.categoriaSeleccionadaId;
    }
    if (this.tiendaSeleccionadaId) {
      filtros.tienda = this.tiendaSeleccionadaId;
    }
    if (this.terminoBusqueda.trim()) {
      filtros.q = this.terminoBusqueda.trim();
    }

    this.catalogoService.listarTodosLosProductos(filtros).subscribe({
      next: (prods) => {
        this.productos = prods;
        // Preservar la variante seleccionada si ya existía
        for (const p of prods) {
          if (p.variantes && p.variantes.length > 0) {
            const currentSelected = this.varianteSeleccionadaPorProducto[p.id];
            const updatedMatch = currentSelected ? p.variantes.find(v => v.id === currentSelected.id) : null;
            this.varianteSeleccionadaPorProducto[p.id] = updatedMatch || p.variantes[0];
          }
        }
        this.cargando = false;
      },
      error: (error: HttpErrorResponse) => {
        this.cargando = false;
        this.mensajeError = this.obtenerMensajeError(error);
      }
    });
  }

  recargarCatalogoSilencioso(): void {
    const filtros: { categoria?: number; tienda?: number; q?: string } = {};
    if (this.categoriaSeleccionadaId) {
      filtros.categoria = this.categoriaSeleccionadaId;
    }
    if (this.tiendaSeleccionadaId) {
      filtros.tienda = this.tiendaSeleccionadaId;
    }
    if (this.terminoBusqueda.trim()) {
      filtros.q = this.terminoBusqueda.trim();
    }

    this.catalogoService.listarTodosLosProductos(filtros).subscribe({
      next: (prods) => {
        this.productos = prods;
        for (const p of prods) {
          if (p.variantes && p.variantes.length > 0) {
            const currentSelected = this.varianteSeleccionadaPorProducto[p.id];
            const updatedMatch = currentSelected ? p.variantes.find(v => v.id === currentSelected.id) : null;
            this.varianteSeleccionadaPorProducto[p.id] = updatedMatch || p.variantes[0];
          }
        }
      },
      error: () => {}
    });
  }

  filtrarPorCategoria(catId: number | null): void {
    this.categoriaSeleccionadaId = catId;
    this.aplicarFiltros();
  }

  filtrarPorTienda(tiendaId: number | null): void {
    this.tiendaSeleccionadaId = tiendaId;
    this.aplicarFiltros();
  }

  seleccionarVariante(productoId: number, variante: VarianteCatalogo): void {
    this.varianteSeleccionadaPorProducto[productoId] = variante;
  }

  obtenerVarianteActual(producto: ProductoCatalogo): VarianteCatalogo | null {
    if (this.varianteSeleccionadaPorProducto[producto.id]) {
      return this.varianteSeleccionadaPorProducto[producto.id];
    }
    return producto.variantes && producto.variantes.length > 0 ? producto.variantes[0] : null;
  }

  obtenerImagenProducto(producto: ProductoCatalogo): string {
    if (producto.imagen_principal) {
      return producto.imagen_principal;
    }
    if (producto.imagenes && producto.imagenes.length > 0) {
      const first = producto.imagenes[0];
      if (typeof first === 'object' && first.url) {
        return first.url;
      }
      return String(first);
    }
    return 'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=600&q=80';
  }

  agregarAlCarrito(producto: ProductoCatalogo): void {
    const variante = this.obtenerVarianteActual(producto);
    if (!variante) {
      this.mensajeError = 'Este producto no tiene variantes disponibles.';
      return;
    }

    if (variante.stock <= 0) {
      this.mensajeError = 'La variante seleccionada no cuenta con stock disponible.';
      return;
    }

    const tiendaId = producto.tienda_id;
    if (!tiendaId) {
      this.mensajeError = 'No se pudo identificar la tienda del producto.';
      return;
    }

    this.limpiarMensajes();
    this.agregandoVarianteId = variante.id;

    this.carritoService.agregarItem({
      tienda_id: tiendaId,
      variante_id: variante.id
    }).subscribe({
      next: () => {
        this.agregandoVarianteId = null;
        this.mensajeExito = `¡Agregado al carrito! ${producto.nombre} (${variante.nombre_variante || variante.nombre})`;
        setTimeout(() => this.limpiarMensajes(), 4000);
      },
      error: (error: HttpErrorResponse) => {
        this.agregandoVarianteId = null;
        this.mensajeError = this.obtenerMensajeError(error);
      }
    });
  }

  limpiarFiltros(): void {
    this.categoriaSeleccionadaId = null;
    this.tiendaSeleccionadaId = null;
    this.terminoBusqueda = '';
    this.aplicarFiltros();
  }

  private limpiarMensajes(): void {
    this.mensajeExito = '';
    this.mensajeError = '';
  }

  private obtenerMensajeError(error: HttpErrorResponse): string {
    const resp = error.error;
    if (typeof resp === 'string' && resp) return resp;
    if (resp?.detail) return resp.detail;
    if (resp && typeof resp === 'object') {
      const key = Object.keys(resp)[0];
      const val = resp[key];
      if (Array.isArray(val) && val.length) return String(val[0]);
      if (val) return String(val);
    }
    return 'Ocurrió un error al procesar la solicitud.';
  }
}
