import { Component, OnInit, OnDestroy, inject, computed } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Subscription, firstValueFrom } from 'rxjs';
import { loadStripe, Stripe, StripeElements, StripePaymentElement } from '@stripe/stripe-js';
import { AuthService } from '../../core/services/auth.service';
import { CarritoService } from '../../core/services/carrito.service';
import { ItemCarritoDetalle } from '../../core/models/carrito.model';

export type MetodoPago = 'efectivo' | 'stripe';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './navbar.component.html',
  styleUrls: ['./navbar.component.css']
})
export class NavbarComponent implements OnInit, OnDestroy {
  public readonly authService = inject(AuthService);
  public readonly carritoService = inject(CarritoService);

  readonly currentUser = toSignal(this.authService.currentUser$, { initialValue: this.authService.currentUser });
  readonly cartData = toSignal(this.carritoService.cartData$, { initialValue: null });
  readonly cartCount = toSignal(this.carritoService.cartCount$, { initialValue: 0 });

  readonly esCliente = computed(() => this.currentUser()?.rol?.toLowerCase() === 'cliente');
  readonly userRole = computed(() => this.currentUser()?.rol?.toLowerCase() ?? '');

  menuOpen = false;
  cartOpen = false;
  checkoutSuccess = false;
  isCheckingOut = false;
  checkoutError: string | null = null;

  // --- Estado de Pasarela Stripe (CU-19) ---
  metodoPago: MetodoPago = 'efectivo';
  cargandoStripe = false;
  pagandoStripe = false;
  stripeError: string | null = null;

  private stripe: Stripe | null = null;
  private elements: StripeElements | null = null;
  private paymentElement: StripePaymentElement | null = null;
  private stripeMontado = false;
  private stripePreload: Promise<{ stripe: Stripe; clientSecret: string }> | null = null;
  private authSub?: Subscription;

  ngOnInit(): void {
    // Cargar carrito inicial exclusivamente para usuarios con rol cliente
    this.authSub = this.authService.currentUser$.subscribe((user) => {
      if (user && user.rol?.toLowerCase() === 'cliente') {
        this.carritoService.cargarCarritoSilencioso();
      }
    });
  }

  ngOnDestroy(): void {
    this.resetPagoStripe();
    this.setCartOpen(false);
    this.authSub?.unsubscribe();
  }

  toggleMenu(): void {
    this.menuOpen = !this.menuOpen;
  }

  abrirEnlaceExterno(ruta: string): void {
    this.menuOpen = false;
    window.open(ruta, '_blank', 'noopener,noreferrer');
  }

  toggleCart(): void {
    if (!this.esCliente()) {
      return;
    }
    this.setCartOpen(!this.cartOpen);
    if (this.cartOpen) {
      this.checkoutSuccess = false;
      this.carritoService.obtenerCarrito().subscribe({
        next: (data) => {
          if (data && data.total_items > 0) {
            this.precargarStripe();
          }
        },
        error: () => {}
      });
    } else {
      this.resetPagoStripe();
    }
  }

  closeCart(): void {
    this.setCartOpen(false);
    this.resetPagoStripe();
  }

  private setCartOpen(open: boolean): void {
    this.cartOpen = open;
    if (typeof document !== 'undefined' && document.body) {
      document.body.style.overflow = open ? 'hidden' : '';
    }
  }

  incrementar(item: ItemCarritoDetalle): void {
    this.resetPagoStripe();
    this.carritoService.actualizarCantidad(item.id, item.cantidad + 1).subscribe();
  }

  decrementar(item: ItemCarritoDetalle): void {
    this.resetPagoStripe();
    if (item.cantidad > 1) {
      this.carritoService.actualizarCantidad(item.id, item.cantidad - 1).subscribe();
    } else {
      this.eliminar(item.id);
    }
  }

  eliminar(itemId: number): void {
    this.resetPagoStripe();
    this.carritoService.eliminarItem(itemId).subscribe();
  }

  vaciar(): void {
    if (confirm('Deseas vaciar todos los productos de tu carrito?')) {
      this.resetPagoStripe();
      this.carritoService.vaciarCarrito().subscribe();
    }
  }

  seleccionarMetodoPago(metodo: MetodoPago): void {
    if (this.metodoPago === metodo) return;
    this.metodoPago = metodo;
    this.checkoutError = null;
    this.stripeError = null;

    if (metodo === 'stripe' && !this.stripeMontado) {
      this.iniciarPagoStripe();
    }
  }

  private precargarStripe(): Promise<{ stripe: Stripe; clientSecret: string }> {
    const preload = firstValueFrom(this.carritoService.crearIntentoPagoStripe()).then(async (intento) => {
      const stripe = await loadStripe(intento.publishable_key);
      if (!stripe) {
        throw new Error('No se pudo inicializar la pasarela de pagos Stripe.');
      }
      return { stripe, clientSecret: intento.client_secret };
    });

    this.stripePreload = preload;
    preload.catch(() => {});
    return preload;
  }

  private iniciarPagoStripe(): void {
    this.cargandoStripe = true;
    this.stripeError = null;
    const preload = this.stripePreload ?? this.precargarStripe();

    preload
      .then(({ stripe, clientSecret }) => {
        this.stripe = stripe;
        this.elements = stripe.elements({ clientSecret });
        this.paymentElement = this.elements.create('payment');
        this.paymentElement.mount('#stripe-payment-element');
        this.stripeMontado = true;
        this.cargandoStripe = false;
      })
      .catch((err) => {
        this.stripeError = err?.error?.error || err?.message || 'No se pudo cargar el formulario seguro de Stripe.';
        this.cargandoStripe = false;
        this.stripePreload = null;
      });
  }

  private resetPagoStripe(): void {
    this.metodoPago = 'efectivo';
    if (this.paymentElement) {
      try {
        this.paymentElement.unmount();
        this.paymentElement.destroy();
      } catch {}
      this.paymentElement = null;
    }
    this.stripe = null;
    this.elements = null;
    this.stripeMontado = false;
    this.stripeError = null;
    this.pagandoStripe = false;
    this.stripePreload = null;

    if (typeof document !== 'undefined') {
      const mountNode = document.getElementById('stripe-payment-element');
      if (mountNode) {
        mountNode.innerHTML = '';
      }
    }
  }

  async pagarConStripe(): Promise<void> {
    if (!this.stripe || !this.elements || this.pagandoStripe) return;
    this.pagandoStripe = true;
    this.stripeError = null;

    try {
      const { error, paymentIntent } = await this.stripe.confirmPayment({
        elements: this.elements,
        redirect: 'if_required',
      });

      if (error) {
        this.stripeError = error.message || 'No se pudo procesar el pago con tarjeta.';
        this.pagandoStripe = false;
        return;
      }

      if (paymentIntent?.status !== 'succeeded') {
        this.stripeError = `El pago con tarjeta no se completo (estado: ${paymentIntent?.status}).`;
        this.pagandoStripe = false;
        return;
      }

      this.carritoService.checkout('stripe', paymentIntent.id).subscribe({
        next: () => {
          this.pagandoStripe = false;
          this.mostrarCheckoutExitoso();
        },
        error: (err) => {
          this.pagandoStripe = false;
          this.stripeError = err.error?.error || 'El pago se debito pero ocurrio un error al registrar el pedido. Contacta a soporte.';
        }
      });
    } catch (err: any) {
      this.pagandoStripe = false;
      this.stripeError = err?.message || 'Error inesperado al conectar con Stripe.';
    }
  }

  procederCheckout(): void {
    if (this.isCheckingOut) return;
    this.isCheckingOut = true;
    this.checkoutError = null;

    this.carritoService.checkout('efectivo').subscribe({
      next: () => {
        this.isCheckingOut = false;
        this.mostrarCheckoutExitoso();
      },
      error: (err) => {
        this.isCheckingOut = false;
        const msg = err.error?.error || err.error?.detail || 'Error al procesar la compra. Verifica la disponibilidad del producto.';
        this.checkoutError = msg;
        alert(msg);
      }
    });
  }

  private mostrarCheckoutExitoso(): void {
    this.checkoutSuccess = true;
    this.checkoutError = null;
    this.resetPagoStripe();
    setTimeout(() => {
      this.setCartOpen(false);
      this.checkoutSuccess = false;
    }, 2800);
  }

  logout(): void {
    this.setCartOpen(false);
    this.authService.logout().subscribe({
      next: () => {},
      error: () => {
        this.authService.clearSession();
      }
    });
  }
}
