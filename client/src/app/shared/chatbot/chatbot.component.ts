import { CommonModule } from '@angular/common';
import {
  AfterViewChecked,
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  ViewChild,
  inject
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { MensajeChat, ProductoCatalogo } from '../../core/models';
import { ChatbotService } from '../../core/services/chatbot.service';
import { MarkdownComponent } from '../markdown/markdown.component';

const IMAGEN_RESPALDO =
  'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=200&q=60';

/**
 * Chatbot de recomendaciones para el cliente: botón flotante + panel.
 *
 * Las respuestas llegan en Markdown; los productos citados se muestran además
 * como tarjetas que abren su ficha (`/producto/:id`). En pantallas angostas el
 * panel ocupa toda la pantalla y se cierra al abrir un producto.
 */
@Component({
  selector: 'app-chatbot',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, MarkdownComponent],
  templateUrl: './chatbot.component.html',
  styleUrls: ['./chatbot.component.css']
})
export class ChatbotComponent implements AfterViewChecked, OnDestroy {
  private readonly chatbot = inject(ChatbotService);

  @ViewChild('lista') lista?: ElementRef<HTMLElement>;
  @ViewChild('entrada') entrada?: ElementRef<HTMLTextAreaElement>;

  abierto = false;
  texto = '';
  mensajes: MensajeChat[] = [];
  enviando = false;

  private bajarAlFinal = false;
  private readonly subs = new Subscription();

  constructor() {
    this.subs.add(this.chatbot.mensajes$.subscribe(m => {
      this.mensajes = m;
      this.bajarAlFinal = true;
    }));
    this.subs.add(this.chatbot.enviando$.subscribe(e => {
      this.enviando = e;
      this.bajarAlFinal = true;
    }));
  }

  ngAfterViewChecked(): void {
    if (this.bajarAlFinal && this.lista) {
      const el = this.lista.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.bajarAlFinal = false;
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  @HostListener('document:keydown.escape')
  alPresionarEscape(): void {
    if (this.abierto) this.cerrar();
  }

  alternar(): void {
    if (this.abierto) {
      this.cerrar();
    } else {
      this.abrir();
    }
  }

  abrir(): void {
    this.abierto = true;
    this.bajarAlFinal = true;
    setTimeout(() => this.entrada?.nativeElement.focus(), 50);
  }

  cerrar(): void {
    this.abierto = false;
  }

  enviar(texto: string = this.texto): void {
    if (!texto.trim() || this.enviando) return;
    this.chatbot.enviar(texto);
    this.texto = '';
    this.ajustarAltura();
  }

  alTeclear(evento: KeyboardEvent): void {
    // Enter envía; Shift+Enter hace salto de línea.
    if (evento.key === 'Enter' && !evento.shiftKey && !evento.isComposing) {
      evento.preventDefault();
      this.enviar();
    }
  }

  ajustarAltura(): void {
    const el = this.entrada?.nativeElement;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  reiniciar(): void {
    this.chatbot.reiniciar();
  }

  /** En móvil el panel tapa la ficha del producto: se cierra al abrirla. */
  alAbrirProducto(): void {
    if (window.matchMedia('(max-width: 640px)').matches) this.cerrar();
  }

  esUltimoDelAsistente(indice: number): boolean {
    return indice === this.mensajes.length - 1 && this.mensajes[indice].rol === 'asistente';
  }

  imagen(producto: ProductoCatalogo): string {
    if (producto.imagen_principal) return producto.imagen_principal;
    const primera = producto.imagenes?.[0];
    if (primera) return typeof primera === 'object' ? primera.url : String(primera);
    return IMAGEN_RESPALDO;
  }

  /** Precio más bajo considerando ofertas, como lo ve el modelo. */
  precio(producto: ProductoCatalogo): string {
    const precios = (producto.variantes || []).map(v => Number(v.precio_oferta ?? v.precio));
    const minimo = precios.length ? Math.min(...precios) : Number(producto.precio_base || 0);
    return minimo.toFixed(2);
  }

  enOferta(producto: ProductoCatalogo): boolean {
    return (producto.variantes || []).some(v => v.precio_oferta !== null && v.precio_oferta !== undefined);
  }

  trackPorIndice(indice: number): number {
    return indice;
  }
}
