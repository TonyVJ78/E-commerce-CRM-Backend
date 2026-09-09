import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  AgregarItemCarritoRequest,
  ItemCarritoCreado,
  ItemCarrito,
  CarritoResumen,
  CarritoResponse,
  CarritoDetalle,
  ItemCarritoDetalle,
} from '../models/carrito.model';

export type {
  AgregarItemCarritoRequest,
  ItemCarritoCreado,
  ItemCarrito,
  CarritoResumen,
  CarritoResponse,
  CarritoDetalle,
  ItemCarritoDetalle,
};

@Injectable({ providedIn: 'root' })
export class CarritoService {
  private readonly apiUrl = `${environment.apiUrl}/pedidos/carrito`;

  private readonly cartCountSubject = new BehaviorSubject<number>(0);
  public readonly cartCount$ = this.cartCountSubject.asObservable();

  private readonly cartDataSubject = new BehaviorSubject<CarritoResponse | null>(null);
  public readonly cartData$ = this.cartDataSubject.asObservable();

  constructor(private readonly http: HttpClient) {
    // Si hay token de usuario, intentar precargar conteo del carrito
    if (localStorage.getItem('km_access_token')) {
      this.cargarCarritoSilencioso();
    }
  }

  cargarCarritoSilencioso(): void {
    this.obtenerCarrito().subscribe({
      next: () => {},
      error: () => {}
    });
  }

  obtenerCarrito(): Observable<CarritoResponse> {
    return this.http.get<CarritoResponse>(`${this.apiUrl}/`).pipe(
      tap((res) => {
        this.cartCountSubject.next(res.total_items || 0);
        this.cartDataSubject.next(res);
      })
    );
  }

  agregarItem(data: AgregarItemCarritoRequest): Observable<ItemCarritoCreado> {
    return this.http.post<ItemCarritoCreado>(`${this.apiUrl}/items/`, data).pipe(
      tap(() => {
        this.cargarCarritoSilencioso();
      })
    );
  }

  actualizarCantidad(itemId: number, cantidad: number): Observable<any> {
    return this.http.patch(`${this.apiUrl}/items/${itemId}/`, { cantidad }).pipe(
      tap(() => {
        this.cargarCarritoSilencioso();
      })
    );
  }

  eliminarItem(itemId: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/items/${itemId}/`).pipe(
      tap(() => {
        this.cargarCarritoSilencioso();
      })
    );
  }

  vaciarCarrito(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/`).pipe(
      tap(() => {
        this.cartCountSubject.next(0);
        this.cartDataSubject.next(null);
      })
    );
  }
}
