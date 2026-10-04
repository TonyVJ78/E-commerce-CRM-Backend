import { Component, inject } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { map } from 'rxjs';
import { NavbarComponent } from './shared/navbar/navbar.component';
import { ChatbotComponent } from './shared/chatbot/chatbot.component';
import { AuthService } from './core/services/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, NavbarComponent, ChatbotComponent, AsyncPipe],
  template: `
    <app-navbar></app-navbar>
    <main class="main-content">
      <router-outlet></router-outlet>
    </main>
    <!-- Chatbot de recomendaciones: solo clientes. Se carga aparte (marked +
         DOMPurify) cuando el navegador queda libre, sin pesar en el arranque. -->
    @if (esCliente$ | async) {
      @defer (on idle) {
        <app-chatbot></app-chatbot>
      }
    }
  `,
  styles: [`
    .main-content {
      min-height: calc(100vh - 64px);
    }
  `]
})
export class AppComponent {
  title = 'Kantu Market';

  readonly esCliente$ = inject(AuthService).currentUser$.pipe(map(u => u?.rol === 'cliente'));
}
