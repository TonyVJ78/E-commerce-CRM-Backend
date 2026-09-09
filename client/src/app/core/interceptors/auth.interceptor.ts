import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const token = authService.getAccessToken();

  let authReq = req;
  if (token) {
    authReq = req.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
  }

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !req.url.includes('login') && !req.url.includes('token/refresh')) {
        return authService.refreshToken().pipe(
          catchError((refreshError) => {
            // Solo cerramos sesión si el refresh en sí falla.
            authService.clearSession();
            return throwError(() => refreshError);
          }),
          switchMap(() => {
            const newToken = authService.getAccessToken();
            const retryReq = req.clone({
              setHeaders: {
                Authorization: `Bearer ${newToken}`
              }
            });
            // El error de la petición reintentada (400, 403, ...) se propaga
            // tal cual al componente; no debe disparar clearSession().
            return next(retryReq);
          })
        );
      }
      return throwError(() => error);
    })
  );
};
