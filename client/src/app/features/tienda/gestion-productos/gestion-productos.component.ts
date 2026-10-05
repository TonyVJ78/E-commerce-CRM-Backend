import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { ProductoService } from '../../../core/services/producto.service';
import { TiendaService } from '../../../core/services/tienda.service';
import { CarritoService } from '../../../core/services/carrito.service';
import { Producto, Tienda, VarianteProducto } from '../../../core/models';
import { MovimientoStock } from '../../../core/services/producto.service';

@Component({
  selector: 'app-gestion-productos',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, RouterLink],
  templateUrl: './gestion-productos.component.html',
  styleUrls: ['./gestion-productos.component.css']
})
export class GestionProductosComponent implements OnInit, OnDestroy {
  productos: Producto[] = [];
  tiendas: Tienda[] = [];
  tiendaSeleccionadaId: number | null = null;
  editForm: FormGroup;

  cargando = false;
  procesandoImagen = false;
  productoEnEdicion: Producto | null = null;
  imagenPreview: string | null = null;
  dragOver = false;
  categoriasDisponibles: string[] = [];
  productoInventario: Producto | null = null;
  varianteInventarioId: number | null = null;
  deltaStock: number | null = null;
  motivoStock = '';
  movimientosStock: MovimientoStock[] = [];
  cargandoHistorial = false;
  guardandoStock = false;
  errorStock = '';
  errorHistorial = '';
  private historialRequest = 0;
  private contextoInventario = 0;

  mensajeExito = '';
  mensajeError = '';
  paginaActual = 1;
  readonly productosPorPagina = 8;

  private readonly subs = new Subscription();

  constructor(
    private readonly fb: FormBuilder,
    private readonly productoService: ProductoService,
    private readonly tiendaService: TiendaService,
    private readonly carritoService: CarritoService
  ) {
    this.editForm = this.fb.group({
      nombre: ['', [Validators.required, Validators.maxLength(200)]],
      precio: [0, [Validators.required, Validators.min(0.01)]],
      categoria: [''],
      imagen_url: [''],
      descripcion: ['']
    });
  }

  ngOnInit(): void {
    this.cargarDatos();

    this.subs.add(
      this.carritoService.checkoutCompleted$.subscribe(() => {
        if (this.tiendaSeleccionadaId) {
          this.cargarProductosDeTienda(this.tiendaSeleccionadaId);
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  cargarDatos(): void {
    this.cargando = true;
    this.tiendaService.listar().subscribe({
      next: (tiendas) => {
        this.tiendas = tiendas;
        if (tiendas.length > 0) {
          this.tiendaSeleccionadaId = tiendas[0].id;
          this.cargarProductosDeTienda(this.tiendaSeleccionadaId);
        } else {
          this.cargando = false;
        }
      },
      error: () => {
        this.mensajeError = 'Error al cargar las tiendas del vendedor.';
        this.cargando = false;
      }
    });
  }

  cambiarTienda(tiendaId: number): void {
    this.tiendaSeleccionadaId = tiendaId;
    this.cargarProductosDeTienda(tiendaId);
  }

  private cargarProductosDeTienda(tiendaId: number): void {
    this.cargando = true;
    this.limpiarMensajes();

    this.productoService.listar(tiendaId).subscribe({
      next: (data) => {
        const tiendaNombre = this.tiendas.find(t => t.id === tiendaId)?.nombre;
        this.productos = (data || []).map(p => {
          const mainVariant = p.variantes && p.variantes.length > 0 ? p.variantes[0] : null;
          const firstImg = p.imagenes && p.imagenes.length > 0 ? p.imagenes[0].url : (p.imagen_url || '');
          return {
            ...p,
            tienda: tiendaId,
            tienda_nombre: tiendaNombre || `Tienda ${tiendaId}`,
            precio: mainVariant ? Number(mainVariant.precio) : (p.precio ? Number(p.precio) : 0),
            stock: p.stock_total !== undefined ? p.stock_total : (mainVariant ? mainVariant.stock : (p.stock || 0)),
            imagen_url: firstImg
          };
        });

        // Extraer categorías únicas para el autocompletado
        const cats = this.productos.map(p => p.categoria).filter(Boolean) as string[];
        this.categoriasDisponibles = Array.from(new Set(cats));

        this.paginaActual = 1;
        this.cargando = false;
      },
      error: () => {
        this.mensajeError = 'Error al cargar los productos de la tienda.';
        this.cargando = false;
      }
    });
  }

  get productosVisibles(): Producto[] {
    const inicio = (this.paginaActual - 1) * this.productosPorPagina;
    return this.productos.slice(inicio, inicio + this.productosPorPagina);
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.productos.length / this.productosPorPagina));
  }

  get paginas(): number[] {
    return Array.from({ length: this.totalPaginas }, (_, index) => index + 1);
  }

  cambiarPagina(pagina: number): void {
    if (pagina >= 1 && pagina <= this.totalPaginas) {
      this.paginaActual = pagina;
    }
  }

  iniciarEdicion(producto: Producto): void {
    this.productoEnEdicion = producto;
    this.limpiarMensajes();
    const currentImg = producto.imagen_url || (producto.imagenes && producto.imagenes.length > 0 ? producto.imagenes[0].url : '');
    this.imagenPreview = currentImg || null;

    this.editForm.patchValue({
      nombre: producto.nombre,
      precio: producto.precio,
      categoria: producto.categoria || '',
      imagen_url: currentImg || '',
      descripcion: producto.descripcion || ''
    });
  }

  cancelarEdicion(): void {
    this.productoEnEdicion = null;
    this.imagenPreview = null;
    this.editForm.reset();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      this.procesarArchivo(input.files[0]);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragOver = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragOver = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.dragOver = false;
    if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
      this.procesarArchivo(event.dataTransfer.files[0]);
    }
  }

  quitarImagen(): void {
    this.imagenPreview = null;
    this.editForm.patchValue({ imagen_url: '' });
  }

  private procesarArchivo(file: File): void {
    if (!file.type.startsWith('image/')) {
      this.mensajeError = 'Por favor selecciona un archivo de imagen válido (JPG, PNG, WebP).';
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      this.mensajeError = 'La imagen es demasiado pesada (máximo 8 MB).';
      return;
    }

    this.procesandoImagen = true;
    const reader = new FileReader();
    reader.onload = (e: ProgressEvent<FileReader>) => {
      const result = e.target?.result as string;
      this.optimizarImagen(result, 1000, 1000, 0.85, (optimizedBase64) => {
        this.procesandoImagen = false;
        this.imagenPreview = optimizedBase64;
        this.editForm.patchValue({ imagen_url: optimizedBase64 });
      });
    };
    reader.onerror = () => {
      this.procesandoImagen = false;
      this.mensajeError = 'Error al leer el archivo desde el dispositivo.';
    };
    reader.readAsDataURL(file);
  }

  private optimizarImagen(dataUrl: string, maxWidth: number, maxHeight: number, quality: number, callback: (result: string) => void): void {
    const img = new Image();
    img.onload = () => {
      let width = img.width;
      let height = img.height;
      if (width > height) {
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }
      } else {
        if (height > maxHeight) {
          width = Math.round((width * maxHeight) / height);
          height = maxHeight;
        }
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(img, 0, 0, width, height);
        const format = dataUrl.startsWith('data:image/png') ? 'image/png' : 'image/jpeg';
        callback(canvas.toDataURL(format, quality));
      } else {
        callback(dataUrl);
      }
    };
    img.onerror = () => callback(dataUrl);
    img.src = dataUrl;
  }

  guardarEdicion(): void {
    if (this.editForm.invalid || !this.productoEnEdicion?.id) return;

    this.cargando = true;
    this.limpiarMensajes();

    const tiendaId = this.productoEnEdicion.tienda || this.tiendaSeleccionadaId || 0;
    const productoId = this.productoEnEdicion.id;
    const { stock: _stockIgnorado, ...datosModificados } = this.editForm.value;

    this.productoService.actualizar(tiendaId, productoId, datosModificados).subscribe({
      next: (prodActualizado) => {
        this.cargando = false;
        this.mensajeExito = `Producto "${prodActualizado.nombre || this.productoEnEdicion?.nombre}" actualizado correctamente.`;
        const idx = this.productos.findIndex(p => p.id === productoId);
        if (idx !== -1) {
          const nuevaImg = datosModificados.imagen_url || prodActualizado.imagen_url || this.productos[idx].imagen_url;
          this.productos[idx] = {
            ...this.productos[idx],
            ...prodActualizado,
            nombre: datosModificados.nombre,
            precio: datosModificados.precio,
            descripcion: datosModificados.descripcion,
            categoria: datosModificados.categoria,
            imagen_url: nuevaImg,
            imagenes: [{ url: nuevaImg, public_id: 'pc-upload' }]
          };
        }
        this.cancelarEdicion();
      },
      error: (err) => {
        this.cargando = false;
        this.mensajeError = err.error?.detail || 'Error al guardar los cambios del producto.';
      }
    });
  }

  abrirInventario(producto: Producto): void {
    if (this.guardandoStock) return;
    this.historialRequest++;
    this.contextoInventario++;
    this.cargandoHistorial = false;
    this.productoInventario = producto;
    this.varianteInventarioId = null;
    this.movimientosStock = [];
    this.deltaStock = null;
    this.motivoStock = '';
    this.errorStock = '';
    this.errorHistorial = '';
  }

  cerrarInventario(): void {
    if (this.guardandoStock) return;
    this.historialRequest++;
    this.contextoInventario++;
    this.cargandoHistorial = false;
    this.productoInventario = null;
    this.varianteInventarioId = null;
    this.movimientosStock = [];
  }

  get varianteInventario(): VarianteProducto | undefined {
    return this.productoInventario?.variantes?.find(v => v.id === this.varianteInventarioId);
  }

  get ajusteStockValido(): boolean {
    const delta = Number(this.deltaStock);
    return !!this.varianteInventario && Number.isInteger(delta) && delta !== 0 && !!this.motivoStock.trim() && this.motivoStock.trim().length <= 255 && this.varianteInventario.stock + delta >= 0;
  }

  get stockProyectado(): number | null {
    return this.varianteInventario && this.deltaStock !== null && Number.isInteger(this.deltaStock) ? this.varianteInventario.stock + this.deltaStock : null;
  }

  seleccionarVariante(id: number): void {
    if (this.guardandoStock || !this.productoInventario?.variantes?.some(v => v.id === id)) return;
    this.varianteInventarioId = id;
    this.contextoInventario++;
    this.movimientosStock = [];
    this.errorHistorial = '';
    const request = ++this.historialRequest;
    const tienda = this.productoInventario.tienda || this.tiendaSeleccionadaId;
    const productoId = this.productoInventario.id;
    if (!tienda) return;
    this.cargandoHistorial = true;
    this.productoService.listarMovimientosStock(tienda, id).subscribe({
      next: rows => { if (request === this.historialRequest && id === this.varianteInventarioId && productoId === this.productoInventario?.id) { this.movimientosStock = rows; this.cargandoHistorial = false; } },
      error: () => { if (request === this.historialRequest && productoId === this.productoInventario?.id) { this.errorHistorial = 'No se pudo cargar el historial de movimientos.'; this.cargandoHistorial = false; } }
    });
  }

  guardarAjusteStock(): void {
    const variant = this.varianteInventario;
    const tienda = this.productoInventario?.tienda || this.tiendaSeleccionadaId;
    const delta = Number(this.deltaStock);
    const reason = this.motivoStock.trim();
    const product = this.productoInventario;
    if (this.guardandoStock || !variant || !product || !tienda || !Number.isInteger(delta) || delta === 0 || !reason || reason.length > 255 || variant.stock + delta < 0) return;
    const productId = product.id;
    const variantId = variant.id;
    const contextId = this.contextoInventario;
    this.guardandoStock = true;
    this.errorStock = '';
    this.productoService.ajustarStock(tienda, variant.id, { delta, reason }).subscribe({
      next: () => {
        this.guardandoStock = false;
        this.productos = this.productos.map(item => {
          if (item.id !== productId) return item;
          const variantes = item.variantes?.map(v => v.id === variantId ? { ...v, stock: v.stock + delta } : v);
          const stock = variantes?.reduce((total, v) => total + v.stock, 0) ?? ((item.stock || 0) + delta);
          return { ...item, variantes, stock, stock_total: stock };
        });
        if (this.productoInventario?.id === productId) {
          this.productoInventario = { ...this.productoInventario, variantes: this.productoInventario.variantes?.map(v => v.id === variantId ? { ...v, stock: v.stock + delta } : v) };
        }
        this.cargarProductosDeTienda(tienda);
        if (contextId === this.contextoInventario && this.productoInventario?.id === productId && this.varianteInventarioId === variantId) {
          this.seleccionarVariante(variantId);
        }
      },
      error: err => {
        this.guardandoStock = false;
        if (this.productoInventario?.id === productId) this.errorStock = err.status === 400 ? (err.error?.detail || err.error?.reason?.[0] || 'El ajuste no es válido; el stock no puede quedar negativo.') : 'No se pudo guardar el ajuste de stock. Comprueba tu conexión e inténtalo de nuevo.';
      }
    });
  }

  eliminar(producto: Producto): void {
    if (!producto.id) return;

    const confirmacion = confirm(`¿Estás seguro de eliminar el producto "${producto.nombre}" de tu catálogo?`);
    if (!confirmacion) return;

    this.cargando = true;
    this.limpiarMensajes();

    const tiendaId = producto.tienda || this.tiendaSeleccionadaId || 0;

    this.productoService.eliminar(tiendaId, producto.id).subscribe({
      next: () => {
        this.cargando = false;
        this.mensajeExito = `Producto "${producto.nombre}" eliminado exitosamente.`;
        this.productos = this.productos.filter(p => p.id !== producto.id);
        if (this.paginaActual > this.totalPaginas) {
          this.paginaActual = this.totalPaginas;
        }
        if (this.productoEnEdicion?.id === producto.id) {
          this.cancelarEdicion();
        }
      },
      error: () => {
        this.cargando = false;
        this.mensajeError = 'No se pudo eliminar el producto.';
      }
    });
  }

  private limpiarMensajes(): void {
    this.mensajeExito = '';
    this.mensajeError = '';
  }
}