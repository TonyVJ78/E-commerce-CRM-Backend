# Kantu Market en Angular 19 (standalone + signals)

Aplica estas reglas cuando el proyecto sea Angular. Los estilos salen de `kantu-tokens.css` y `kantu-components.css` (cargados en `styles.scss` o `angular.json`), más SCSS encapsulado por componente. No añadas Tailwind ni Bootstrap.

## Reglas
1. Todos los componentes son `standalone: true`.
2. Control de flujo nuevo: `@if`, `@else`, `@for (... ; track item.id)`, `@empty`. No uses `*ngIf` ni `*ngFor`.
3. Estado con `signal()` y `computed()`; dependencias con `inject()`.
4. Todo listado o bloque con datos implementa **tres estados**: carga (skeleton), vacío (icono SVG + acción) y error (alerta roja con qué hacer).
5. Cero emojis; iconos SVG de trazo (Lucide/Heroicons outline) con la clase `.icon`.
6. `aria-label` en botones solo-icono; `routerLinkActive="is-active"` junto con `ariaCurrentWhenActive="page"` en la navegación.
7. Enlaces a recursos externos (Django admin, backups): usa un `<a href target="_blank" rel="noopener">` con icono de enlace externo; evita `(click)` con `window.open` salvo que haga falta lógica. Lee la URL del `environment`, no la dejes escrita en la plantilla.

## Los tres estados
```html
@if (cargando()) {
  <div class="bento">
    @for (n of [1,2,3,4]; track n) { <div class="col-3 skeleton" style="height:112px"></div> }
  </div>
} @else if (error()) {
  <div class="alert alert--danger" role="alert">
    No pudimos cargar los datos. <button class="btn btn--ghost" (click)="cargar()">Reintentar</button>
  </div>
} @else {
  @for (p of productos(); track p.id) {
    <article class="product"> ... </article>
  } @empty {
    <div class="empty">
      <svg class="empty__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.6a1 1 0 00-.7.3l-2.4 2.4a1 1 0 01-.7.3h-3.2a1 1 0 01-.7-.3l-2.4-2.4a1 1 0 00-.7-.3H4"/>
      </svg>
      <h3>Aún no hay productos</h3>
      <p>Cuando agregues productos, aparecerán aquí.</p>
      <a class="btn btn--primary" routerLink="/inventario/nuevo">Agregar producto</a>
    </div>
  }
}
```

## Componente con signals
```ts
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TiendaService } from '@core/services/tienda.service';

interface Metricas { ingresos_totales: number; total_pedidos: number; pedidos_pendientes: number; productos_activos: number; }

@Component({
  selector: 'app-panel-vendedor',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './panel-vendedor.component.html',
  styleUrl: './panel-vendedor.component.scss',
})
export class PanelVendedorComponent implements OnInit {
  private tienda = inject(TiendaService);

  cargando = signal(true);
  error = signal(false);
  metricas = signal<Metricas | null>(null);

  ingresos = computed(() =>
    `Bs ${(this.metricas()?.ingresos_totales ?? 0).toLocaleString('es-BO', { minimumFractionDigits: 2 })}`);

  ngOnInit() { this.cargar(); }

  cargar() {
    this.cargando.set(true); this.error.set(false);
    this.tienda.obtenerMetricas().subscribe({
      next: m => { this.metricas.set(m); this.cargando.set(false); },
      error: () => { this.error.set(true); this.cargando.set(false); },
    });
  }
}
```

## Navbar (iconos SVG, sin emojis)
```html
<header class="nav">
  <div class="layout nav__inner">
    <a routerLink="/" class="logo">Kantu Market</a>
    <nav class="nav__links" aria-label="Principal">
      <a routerLink="/admin" routerLinkActive="is-active" ariaCurrentWhenActive="page" class="nav__link">Dashboard</a>
      <a routerLink="/admin/auditoria" routerLinkActive="is-active" ariaCurrentWhenActive="page" class="nav__link">Auditoría</a>
      <a routerLink="/admin/accesos" routerLinkActive="is-active" ariaCurrentWhenActive="page" class="nav__link">Roles y permisos</a>
      <a [href]="urlBackups" target="_blank" rel="noopener" class="nav__link">
        Backups
        <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
      </a>
      <span class="badge badge--admin">Administrador</span>
      <button type="button" class="btn btn--outline">Cerrar sesión</button>
    </nav>
  </div>
</header>
```
