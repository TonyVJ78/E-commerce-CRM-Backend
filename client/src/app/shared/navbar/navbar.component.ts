import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CarritoService } from '../../core/services/carrito.service';
import { ItemCarritoDetalle } from '../../core/models/carrito.model';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './navbar.component.html',
  styleUrls: ['./navbar.component.css']
})
export class NavbarComponent implements OnInit {
  menuOpen = false;
  cartOpen = false;
  checkoutSuccess = false;

  constructor(
    public authService: AuthService,
    public carritoService: CarritoService
  ) {}

  ngOnInit(): void {
    // Si el usuario es cliente, cargar carrito inicial
    this.authService.currentUser$.subscribe(user => {
      if (user && user.rol === 'cliente') {
        this.carritoService.cargarCarritoSilencioso();
      }
    });
  }

  toggleMenu(): void {
    this.menuOpen = !this.menuOpen;
  }

  toggleCart(): void {
    this.cartOpen = !this.cartOpen;
    if (this.cartOpen) {
      this.checkoutSuccess = false;
      this.carritoService.cargarCarritoSilencioso();
    }
  }

  closeCart(): void {
    this.cartOpen = false;
  }

  incrementar(item: ItemCarritoDetalle): void {
    this.carritoService.actualizarCantidad(item.id, item.cantidad + 1).subscribe();
  }

  decrementar(item: ItemCarritoDetalle): void {
    if (item.cantidad > 1) {
      this.carritoService.actualizarCantidad(item.id, item.cantidad - 1).subscribe();
    } else {
      this.eliminar(item.id);
    }
  }

  eliminar(itemId: number): void {
    this.carritoService.eliminarItem(itemId).subscribe();
  }

  vaciar(): void {
    if (confirm('¿Deseas vaciar todos los productos de tu carrito?')) {
      this.carritoService.vaciarCarrito().subscribe();
    }
  }

  procederCheckout(): void {
    this.checkoutSuccess = true;
    setTimeout(() => {
      this.carritoService.vaciarCarrito().subscribe();
      setTimeout(() => {
        this.cartOpen = false;
        this.checkoutSuccess = false;
      }, 2500);
    }, 1200);
  }

  logout(): void {
    this.cartOpen = false;
    this.authService.logout().subscribe({
      next: () => {},
      error: () => {
        this.authService.clearSession();
      }
    });
  }
}
