import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Obtiene la ruta de redirección según el rol del usuario autenticado.
 */
function getRoleHomePath(rol: string | null | undefined): string {
  switch (rol) {
    case 'cliente':
      return '/inicio';
    case 'administrador':
      return '/dashboard';
    case 'empresa':
      return '/tiendas';
    default:
      return '/perfil';
  }
}

/**
 * Protege rutas que requieren estar autenticado (cualquier rol).
 */
export const authGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated) {
    return true;
  }
  router.navigate(['/login']);
  return false;
};

/**
 * Permite acceso solo a usuarios invitados / no autenticados (login, registro).
 */
export const guestGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.isAuthenticated) {
    return true;
  }
  router.navigate([getRoleHomePath(authService.currentUser?.rol)]);
  return false;
};

/**
 * Fábrica genérica de guard por rol con redirección automática.
 */
function createRoleGuard(requiredRole: 'cliente' | 'empresa' | 'administrador'): CanActivateFn {
  return () => {
    const authService = inject(AuthService);
    const router = inject(Router);

    if (!authService.isAuthenticated) {
      router.navigate(['/login']);
      return false;
    }

    const rol = authService.currentUser?.rol;
    if (rol === requiredRole) {
      return true;
    }

    router.navigate([getRoleHomePath(rol)]);
    return false;
  };
}

export const clienteGuard: CanActivateFn = createRoleGuard('cliente');
export const empresaGuard: CanActivateFn = createRoleGuard('empresa');
export const adminGuard: CanActivateFn = createRoleGuard('administrador');
