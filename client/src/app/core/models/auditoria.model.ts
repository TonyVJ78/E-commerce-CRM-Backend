export interface BitacoraAcceso {
  id: number;
  usuario: number | null;
  usuario_email: string | null;
  usuario_nombre?: string | null;
  email_intento: string;
  ip: string;
  user_agent?: string;
  dispositivo?: string;
  exitoso: boolean;
  motivo?: string;
  motivo_falla?: string;
  fecha: string;
}

export interface LogAuditoria {
  id: number;
  usuario: number | null;
  usuario_email: string | null;
  tabla_afectada: string;
  registro_id: number | string;
  accion: 'CREAR' | 'EDITAR' | 'ELIMINAR' | 'LOGOUT' | 'LOGIN_FALLIDO' | string;
  ip?: string;
  fecha: string;
  datos_anteriores?: Record<string, any> | null;
  datos_nuevos?: Record<string, any> | null;
}

export interface FiltrosBitacora {
  usuario?: string;
  ip?: string;
  exitoso?: boolean | '';
  fecha_desde?: string;
  fecha_hasta?: string;
  page?: number;
  page_size?: number;
}

export interface FiltrosLogs {
  usuario?: string;
  tabla?: string;
  accion?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  page?: number;
  page_size?: number;
}
