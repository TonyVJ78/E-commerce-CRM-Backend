export interface Permiso {
  id: number;
  codigo: string;   // "<modulo>.<accion>"
  nombre: string;
  modulo: string;
  accion?: string;  // 'ver' | 'crear' | 'editar' | 'eliminar'
  descripcion?: string;
}

export interface Rol {
  id: number;
  nombre: string;
  descripcion?: string;
  es_sistema?: boolean;
  es_semilla?: boolean;
  usuarios_count?: number;
  permisos: Permiso[];
}

export interface PermisosDeRol {
  asignados: number[];
  disponibles: Permiso[];
}

export interface RolRef {
  id: number;
  nombre: string;
}

export interface UsuarioAdmin {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  rol: RolRef | Rol | null;
  activo?: boolean;
  is_active: boolean;
  is_staff?: boolean;
  fecha_registro?: string;
  date_joined?: string;
  ultimo_acceso?: string;
}

export interface FiltrosUsuarios {
  rol?: string;
  activo?: boolean;
  buscar?: string;
  page?: number;
  page_size?: number;
}

export interface PermisoMatriz {
  id: number;
  codigo: string;
  nombre: string;
  asignado: boolean;
}

export interface MatrizPermisos {
  rol: Rol;
  modulos: {
    [modulo: string]: {
      [accion: string]: PermisoMatriz;
    };
  };
}
