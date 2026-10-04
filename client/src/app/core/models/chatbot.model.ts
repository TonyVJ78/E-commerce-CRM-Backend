import { ProductoCatalogo } from './catalogo.model';

export type RolMensajeChat = 'usuario' | 'asistente';

/** Mensaje tal como viaja al backend (`POST /api/ia/chatbot/`). */
export interface MensajeChatApi {
  rol: RolMensajeChat;
  contenido: string;
}

export interface ChatbotResponse {
  /** Markdown; los productos se enlazan como `[Nombre](producto:ID)`. */
  mensaje: string;
  /** Productos citados en el mensaje, en el orden en que aparecen. */
  productos: ProductoCatalogo[];
  /** Respuestas rápidas que el cliente puede tocar. */
  sugerencias: string[];
}

/** Mensaje de la conversación en pantalla. */
export interface MensajeChat extends MensajeChatApi {
  productos?: ProductoCatalogo[];
  sugerencias?: string[];
  error?: boolean;
}
