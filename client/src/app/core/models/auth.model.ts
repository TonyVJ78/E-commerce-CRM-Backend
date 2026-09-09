export type UserRole = 'administrador' | 'empresa' | 'cliente';

export interface Usuario {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  rol: string | null;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  usuario: Usuario;
}

export interface RegistroData {
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  rol_id?: number;
}

export interface PerfilUpdateData {
  first_name: string;
  last_name: string;
}
