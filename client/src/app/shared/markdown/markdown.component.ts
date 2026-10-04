import { Component, EventEmitter, HostListener, Input, OnChanges, Output, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { Router } from '@angular/router';
import DOMPurify from 'dompurify';
import { Marked } from 'marked';

const marked = new Marked({ gfm: true, breaks: true });

/** `[Nombre](producto:12)` → enlace interno a la ficha del producto. */
const ENLACE_PRODUCTO = /\]\(producto:(\d+)\)/g;
const RUTA_PRODUCTO = /^\/producto\/(\d+)$/;

// Una sola vez para toda la app: los enlaces a productos se marcan para
// interceptarlos y los externos se abren en otra pestaña.
DOMPurify.addHook('afterSanitizeAttributes', nodo => {
  if (nodo.tagName !== 'A') return;
  const href = nodo.getAttribute('href') || '';
  const producto = RUTA_PRODUCTO.exec(href);
  if (producto) {
    nodo.setAttribute('data-producto', producto[1]);
    nodo.setAttribute('class', 'md-producto');
  } else {
    nodo.setAttribute('target', '_blank');
    nodo.setAttribute('rel', 'noopener noreferrer');
  }
});

/**
 * Renderiza Markdown (del chatbot) de forma segura.
 *
 * `marked` lo convierte a HTML y DOMPurify lo limpia antes de insertarlo, así
 * que un texto con `<script>` o `onerror=` nunca llega al DOM. Los enlaces
 * `producto:ID` se navegan con el router; con Ctrl/Cmd o clic central el
 * navegador los abre en otra pestaña como cualquier enlace.
 */
@Component({
  selector: 'app-markdown',
  standalone: true,
  template: `<div class="md" [innerHTML]="html"></div>`,
  styleUrls: ['./markdown.component.css']
})
export class MarkdownComponent implements OnChanges {
  private readonly sanitizer = inject(DomSanitizer);
  private readonly router = inject(Router);

  @Input() texto = '';
  /** Se emite al navegar a un producto desde el texto. */
  @Output() productoAbierto = new EventEmitter<number>();

  html: SafeHtml = '';

  ngOnChanges(): void {
    const fuente = (this.texto || '').replace(ENLACE_PRODUCTO, '](/producto/$1)');
    const crudo = marked.parse(fuente, { async: false }) as string;
    const limpio = DOMPurify.sanitize(crudo, { ADD_ATTR: ['target'] });
    // Ya pasó por DOMPurify; el sanitizador de Angular borraría los data-*.
    this.html = this.sanitizer.bypassSecurityTrustHtml(limpio);
  }

  @HostListener('click', ['$event'])
  alHacerClic(evento: MouseEvent): void {
    const enlace = (evento.target as HTMLElement).closest('a[data-producto]');
    if (!enlace) return;
    if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.button !== 0) return;

    evento.preventDefault();
    const id = Number(enlace.getAttribute('data-producto'));
    this.router.navigate(['/producto', id]);
    this.productoAbierto.emit(id);
  }
}
