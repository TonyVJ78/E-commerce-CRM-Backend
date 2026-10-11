export interface BackupItem {
  id: string;
  nombre: string;
  tamano_bytes: number;
  tamano_formateado: string;
  fecha_creacion: string;
  tipo: 'manual' | 'automatico' | string;
  tablas_incluidas: number;
}

export interface ResumenBackups {
  total_archivos: number;
  espacio_total_mb: number;
  ultimo_respaldo: string | null;
}

export interface ResumenBackupsResponse {
  backups: BackupItem[];
  resumen: ResumenBackups;
}

export interface RespaldoGeneradoResponse {
  success: boolean;
  mensaje: string;
  backup: BackupItem;
}

export interface ConfigAutomatizacion {
  activo: boolean;
  frecuencia: 'diaria' | 'semanal' | string;
  hora_ejecucion: string;
  retencion_dias: number;
  proxima_ejecucion?: string | null;
}
