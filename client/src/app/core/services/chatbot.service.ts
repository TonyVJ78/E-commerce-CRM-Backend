import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ChatbotResponse, MensajeChat, MensajeChatApi } from '../models/chatbot.model';
import { AuthService } from './auth.service';

const SALUDO: MensajeChat = {
  rol: 'asistente',
  contenido:
    '¡Hola! Soy **Kantu**, tu asistente de compras. Cuéntame qué buscas ' +
    '—aunque sea una idea general— y te ayudo a encontrarlo en las tiendas.',
  sugerencias: ['Busco un regalo', 'Algo de alpaca', 'Café boliviano', 'Ofertas de hoy']
};

/**
 * Conversación con el chatbot de recomendaciones.
 *
 * El backend no guarda el historial: se manda completo en cada mensaje. Aquí
 * vive mientras dure la pestaña (sessionStorage, por usuario) para que la
 * conversación siga ahí al navegar a un producto y volver.
 */
@Injectable({ providedIn: 'root' })
export class ChatbotService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);

  private readonly apiUrl = `${environment.apiUrl}/ia/chatbot/`;
  private readonly mensajesSubject = new BehaviorSubject<MensajeChat[]>([SALUDO]);
  readonly mensajes$ = this.mensajesSubject.asObservable();
  private readonly enviandoSubject = new BehaviorSubject<boolean>(false);
  readonly enviando$ = this.enviandoSubject.asObservable();

  private claveUsuario: string | null = null;

  constructor() {
    this.authService.currentUser$.subscribe(usuario => {
      this.claveUsuario = usuario ? `km_chat_${usuario.id}` : null;
      this.mensajesSubject.next(this.leerGuardados());
    });
  }

  get enviando(): boolean {
    return this.enviandoSubject.value;
  }

  enviar(texto: string): void {
    const contenido = texto.trim();
    if (!contenido || this.enviando) return;

    // Los mensajes con error no se reenvían: confundirían al modelo.
    const conversacion = [
      ...this.mensajesSubject.value.filter(m => !m.error),
      { rol: 'usuario', contenido } as MensajeChat
    ];
    this.publicar(conversacion);
    this.enviandoSubject.next(true);

    const historial: MensajeChatApi[] = conversacion.map(({ rol, contenido: c }) => ({ rol, contenido: c }));

    this.http.post<ChatbotResponse>(this.apiUrl, { mensajes: historial }).subscribe({
      next: res => {
        this.enviandoSubject.next(false);
        this.publicar([
          ...conversacion,
          {
            rol: 'asistente',
            contenido: res.mensaje,
            productos: res.productos ?? [],
            sugerencias: res.sugerencias ?? []
          }
        ]);
      },
      error: (error: HttpErrorResponse) => {
        this.enviandoSubject.next(false);
        this.publicar([
          ...conversacion,
          { rol: 'asistente', contenido: this.mensajeError(error), error: true }
        ]);
      }
    });
  }

  reiniciar(): void {
    if (this.enviando) return;
    this.publicar([SALUDO]);
  }

  private publicar(mensajes: MensajeChat[]): void {
    this.mensajesSubject.next(mensajes);
    if (!this.claveUsuario) return;
    try {
      sessionStorage.setItem(this.claveUsuario, JSON.stringify(mensajes));
    } catch {
      // Sin almacenamiento la conversación solo dura hasta recargar.
    }
  }

  private leerGuardados(): MensajeChat[] {
    if (!this.claveUsuario) return [SALUDO];
    try {
      const guardados = JSON.parse(sessionStorage.getItem(this.claveUsuario) || 'null');
      return Array.isArray(guardados) && guardados.length ? guardados : [SALUDO];
    } catch {
      return [SALUDO];
    }
  }

  private mensajeError(error: HttpErrorResponse): string {
    if (error.status === 429) {
      return 'Vas muy rápido 😅. Espera un momento y vuelve a intentarlo.';
    }
    if (error.status === 0) {
      return 'No pude conectarme con el servidor. Revisa tu conexión e intenta de nuevo.';
    }
    return error.error?.detail || 'No pude responder ahora. Intenta de nuevo en unos segundos.';
  }
}
