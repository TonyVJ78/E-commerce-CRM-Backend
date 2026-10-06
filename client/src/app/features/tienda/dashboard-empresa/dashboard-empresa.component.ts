import { Component, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TiendaService, DashboardMetrics, VentaDia } from '../../../core/services/tienda.service';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-dashboard-empresa',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard-empresa.component.html',
  styles: [`
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }
    .metric-card {
      background-color: #ffffff;
      border-radius: 0.5rem;
      padding: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      border: 1px solid #f3f4f6;
      transition: all 0.2s;
    }
    .metric-card:hover {
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
      transform: translateY(-2px);
    }
    .metric-card.clickable {
      cursor: pointer;
      text-decoration: none;
      display: block;
    }
    .metric-card.clickable:hover {
      border-color: #c8102e;
      box-shadow: 0 4px 12px rgba(200, 16, 46, 0.12);
      transform: translateY(-2px);
    }
    .metric-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }
    .metric-header h3 {
      font-size: 0.875rem;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 0;
    }
    .metric-value {
      font-size: 1.875rem;
      font-weight: 700;
      color: #1f2937;
      margin: 0;
    }
    .metric-subtext {
      font-size: 0.875rem;
      font-weight: 400;
      color: #9ca3af;
    }
    .icon-container {
      padding: 0.5rem;
      border-radius: 0.5rem;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .icon-green { background-color: #dcfce7; color: #16a34a; }
    .icon-yellow { background-color: #fef9c3; color: #ca8a04; }
    .icon-blue { background-color: #dbeafe; color: #2563eb; }
    .icon-purple { background-color: #f3e8ff; color: #9333ea; }
    .icon-red { background-color: #fee2e2; color: #dc2626; }
    .status-alert { font-size: 0.875rem; color: #ef4444; margin-top: 0.5rem; }
    .status-ok { font-size: 0.875rem; color: #22c55e; margin-top: 0.5rem; }
    .loading-state { text-align: center; padding: 4rem; color: #6b7280; }
    .error-state { background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 1rem; color: #b91c1c; max-width: 1200px; margin: 0 auto 2rem; }
    
    .chart-container {
      background-color: #ffffff;
      border-radius: 0.5rem;
      padding: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      border: 1px solid #f3f4f6;
      margin-top: 2rem;
      height: 400px;
    }
    .chart-container h3 {
      font-size: 1.25rem;
      font-weight: 600;
      color: #111827;
      margin-bottom: 1.5rem;
    }

    .fallback-chart-container {
      height: 85%;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      padding: 1rem 0;
    }
    .fallback-bars-grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 0.75rem;
      height: 240px;
      align-items: end;
    }
    .fallback-bar-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      height: 100%;
      justify-content: flex-end;
    }
    .fallback-bar-track {
      width: 100%;
      max-width: 48px;
      height: 180px;
      background: #f3f4f6;
      border-radius: 6px;
      display: flex;
      align-items: flex-end;
      overflow: hidden;
    }
    .fallback-bar-fill {
      width: 100%;
      background: #c8102e;
      border-radius: 6px 6px 0 0;
      transition: height 0.3s ease;
      min-height: 4px;
    }
    .fallback-bar-val {
      font-size: 0.85rem;
      font-weight: 700;
      color: #1f2937;
      margin-top: 0.35rem;
    }
    .fallback-bar-label {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.2rem;
    }

    @media (max-width: 640px) {
      .metrics-grid {
        grid-template-columns: 1fr;
        gap: 0.85rem;
        margin-bottom: 1.25rem;
      }
      .metric-card {
        padding: 1.15rem;
      }
      .chart-container {
        padding: 1rem;
        height: 280px;
        margin-top: 1.25rem;
      }
      .chart-container h3 {
        font-size: 1.05rem;
        margin-bottom: 1rem;
      }
    }
  `]
})
export class DashboardEmpresaComponent implements OnInit {
  metrics: DashboardMetrics | null = null;
  loading: boolean = true;
  error: string | null = null;
  chart: any;
  usarFallback = false;

  @ViewChild('ventasChart') ventasChart!: ElementRef;

  constructor(private tiendaService: TiendaService) {}

  ngOnInit(): void {
    this.cargarMetricas();
  }

  get ventasSemana(): VentaDia[] {
    if (!this.metrics) return [];
    const lista = (this.metrics as any).grafico_ventas || (this.metrics as any).ventas_semana;
    if (Array.isArray(lista) && lista.length > 0) {
      return lista;
    }
    const dias: VentaDia[] = [];
    const hoy = new Date();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(hoy);
      d.setDate(d.getDate() - i);
      const diaStr = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
      dias.push({ fecha: diaStr, cantidad: 0 });
    }
    return dias;
  }

  get maxVentaSemana(): number {
    const vals = this.ventasSemana.map(v => v.cantidad || 0);
    const max = Math.max(...vals, 0);
    return max > 0 ? max : 1;
  }

  cargarMetricas(): void {
    this.loading = true;
    this.tiendaService.getDashboardMetrics().subscribe({
      next: (data) => {
        this.metrics = data;
        this.loading = false;
        setTimeout(() => {
          this.createChart();
        }, 0);
      },
      error: (err) => {
        this.error = 'No se pudieron cargar las metricas. Verifica tu conexion o intenta mas tarde.';
        this.loading = false;
        console.error('Error cargando metricas del dashboard:', err);
      }
    });
  }

  createChart(): void {
    if (!this.ventasChart?.nativeElement) {
      this.usarFallback = true;
      return;
    }

    try {
      if (this.chart) {
        this.chart.destroy();
        this.chart = null;
      }

      const ventas = this.ventasSemana;
      const labels = ventas.map(v => v.fecha);
      const data = ventas.map(v => v.cantidad || 0);

      this.chart = new Chart(this.ventasChart.nativeElement, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Productos Vendidos',
            data: data,
            backgroundColor: 'rgba(200, 16, 46, 0.8)',
            borderColor: '#C8102E',
            borderWidth: 1,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { stepSize: 1 }
            }
          }
        }
      });
      this.usarFallback = false;
    } catch (err) {
      console.warn('Error inicializando Chart.js, activando fallback visual CSS:', err);
      this.usarFallback = true;
    }
  }
}
