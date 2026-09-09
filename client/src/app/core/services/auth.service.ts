import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import {
  Usuario,
  LoginResponse,
  RegistroData,
  PerfilUpdateData,
  UserRole
} from '../models/auth.model';

export type { Usuario, LoginResponse, RegistroData, PerfilUpdateData, UserRole };

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly apiUrl = `${environment.apiUrl}/auth`;
  private readonly currentUserSubject = new BehaviorSubject<Usuario | null>(null);
  public readonly currentUser$ = this.currentUserSubject.asObservable();

  constructor(
    private readonly http: HttpClient,
    private readonly router: Router
  ) {
    this.loadUserFromStorage();
  }

  private loadUserFromStorage(): void {
    const userData = localStorage.getItem('km_user');
    if (userData) {
      try {
        this.currentUserSubject.next(JSON.parse(userData));
      } catch {
        localStorage.removeItem('km_user');
      }
    }
  }

  get isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  get currentUser(): Usuario | null {
    return this.currentUserSubject.value;
  }

  getAccessToken(): string | null {
    return localStorage.getItem('km_access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('km_refresh_token');
  }

  registro(data: RegistroData): Observable<any> {
    return this.http.post(`${this.apiUrl}/registro/`, data);
  }

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/login/`, { email, password }).pipe(
      tap(response => {
        localStorage.setItem('km_access_token', response.access);
        localStorage.setItem('km_refresh_token', response.refresh);
        localStorage.setItem('km_user', JSON.stringify(response.usuario));
        this.currentUserSubject.next(response.usuario);
      })
    );
  }

  logout(): Observable<any> {
    const refresh = this.getRefreshToken();
    return this.http.post(`${this.apiUrl}/logout/`, { refresh }).pipe(
      tap(() => this.clearSession())
    );
  }

  clearSession(): void {
    localStorage.removeItem('km_access_token');
    localStorage.removeItem('km_refresh_token');
    localStorage.removeItem('km_user');
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  refreshToken(): Observable<any> {
    const refresh = this.getRefreshToken();
    return this.http.post<any>(`${this.apiUrl}/token/refresh/`, { refresh }).pipe(
      tap(response => {
        localStorage.setItem('km_access_token', response.access);
        if (response.refresh) {
          localStorage.setItem('km_refresh_token', response.refresh);
        }
      })
    );
  }

  getPerfil(): Observable<any> {
    return this.http.get(`${this.apiUrl}/perfil/`);
  }

  updatePerfil(data: PerfilUpdateData): Observable<any> {
    return this.http.patch(`${this.apiUrl}/perfil/`, data).pipe(
      tap((updatedUser: any) => {
        const current = this.currentUser;
        if (current) {
          const merged = { ...current, ...updatedUser };
          localStorage.setItem('km_user', JSON.stringify(merged));
          this.currentUserSubject.next(merged);
        }
      })
    );
  }

  requestPasswordReset(email: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/password-reset/`, { email });
  }

  confirmPasswordReset(
    uid: string,
    token: string,
    new_password: string,
    new_password_confirm: string
  ): Observable<any> {
    return this.http.post(`${this.apiUrl}/password-reset-confirm/`, {
      uid,
      token,
      new_password,
      new_password_confirm
    });
  }
}
