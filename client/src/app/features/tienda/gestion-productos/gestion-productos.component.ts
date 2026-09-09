import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ProductoService } from '../../../core/services/producto.service';
import { TiendaService } from '../../../core/services/tienda.service';
import { Producto, Tienda } from '../../../core/models';

@Component({
  selector: 'app-gestion-productos',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './gestion-productos.component.html',
  styleUrls: ['./gestion-productos.component.css']
})
export class GestionProductosComponent implements OnInit {
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

  mensajeExito = '';
  mensajeError = '';
  paginaActual = 1;
  readonly productosPorPagina = 8;

  constructor(
    private readonly fb: FormBuilder,
    private readonly productoService: ProductoService,
    private readonly tiendaService: TiendaService
  ) {
    this.editForm = this.fb.group({
      nombre: ['', [Validators.required, Validators.maxLength(200)]],
      precio: [0, [Validators.required, Validators.min(0.01)]],
      stock: [0, [Validators.required, Validators.min(0)]],
      categoria: [''],
      imagen_url: [''],
      descripcion: ['']
    });
  }

  ngOnInit(): void {
    this.cargarDatos();
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
      stock: producto.stock,
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
    const datosModificados = this.editForm.value;

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
            stock: datosModificados.stock,
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