import { Routes } from '@angular/router';
import { authGuard, guestGuard, empresaGuard, adminGuard, clienteGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'login',
    pathMatch: 'full'
  },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/login/login.component').then(m => m.LoginComponent)
  },
  {
    path: 'registro',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/register/register.component').then(m => m.RegisterComponent)
  },
  {
    path: 'recuperar-password',
    loadComponent: () =>
      import('./features/auth/password-recovery/password-recovery.component').then(m => m.PasswordRecoveryComponent)
  },
  {
    path: 'recuperar-password/:uid/:token',
    loadComponent: () =>
      import('./features/auth/password-recovery/password-recovery.component').then(m => m.PasswordRecoveryComponent)
  },
  {
    path: 'inicio',
    canActivate: [clienteGuard],
    loadComponent: () =>
      import('./features/home/home-cliente.component').then(m => m.HomeClienteComponent)
  },
  {
    path: 'pedidos',
    canActivate: [clienteGuard],
    loadComponent: () =>
      import('./features/cliente/pedidos/pedidos.component').then(m => m.PedidosClienteComponent)
  },
  {
    path: 'mis-pedidos',
    redirectTo: 'pedidos',
    pathMatch: 'full'
  },
  {
    path: 'producto/:id',
    loadComponent: () =>
      import('./features/producto/detalle-producto/detalle-producto.component').then(
        m => m.DetalleProductoComponent
      )
  },

  {
    path: 'dashboard',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/admin/dashboard-admin.component').then(m => m.DashboardAdminComponent)
  },
  {
    path: 'auditoria',
    canActivate: [adminGuard],
    loadComponent: () =>
      import('./features/admin/auditoria/auditoria.component').then(m => m.AuditoriaComponent)
  },
  {
    path: 'accesos',
    canActivate: [adminGuard],
    loadComponent: () =>
      import('./features/admin/accesos/accesos.component').then(m => m.AccesosComponent)
  },
  {
    path: 'perfil',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/profile/profile.component').then(m => m.ProfileComponent)
  },
  {
    path: 'tiendas',
    canActivate: [empresaGuard],
    loadComponent: () =>
       import('./features/tienda/create-tienda/create-tienda.component').then(m => m.CreateTiendaComponent)
  },
  {
    path: 'tiendas/productos',
    canActivate: [empresaGuard],
    loadComponent: () =>
      import('./features/tienda/gestion-productos/gestion-productos.component').then(m => m.GestionProductosComponent)
  },
  {
    path: 'tiendas/pedidos',
    canActivate: [empresaGuard],
    loadComponent: () =>
      import('./features/tienda/gestion-pedidos/gestion-pedidos.component').then(m => m.GestionPedidosComponent)
  },
  {
    path: 'tiendas/identidad',
    canActivate: [empresaGuard],
    loadComponent: () =>
      import('./features/tienda/identidad-marca/identidad-marca.component').then(m => m.IdentidadMarcaComponent)
  },
  {
    path: 'tiendas/:tiendaId/productos/nuevo',
    canActivate: [empresaGuard],
    loadComponent: () =>
      import('./features/producto/create-producto/create-producto.component').then(m => m.CreateProductoComponent)
  },
  {
    path: 'panel-vendedor',
    canActivate: [empresaGuard],
    loadComponent: () =>
      import('./features/tienda/dashboard-empresa/dashboard-empresa.component').then(m => m.DashboardEmpresaComponent)
  },
  {
    path: '**',
    redirectTo: 'login'
  }
];
