import { Component, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TiendaService, DashboardMetrics } from '../../../core/services/tienda.service';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-dashboard-empresa',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard-empresa.component.html',
  styles: [`
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1.5rem;
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
  `]
})
export class DashboardEmpresaComponent implements OnInit {
  metrics: DashboardMetrics | null = null;
  loading: boolean = true;
  error: string | null = null;
  chart: any;

  @ViewChild('ventasChart') ventasChart!: ElementRef;

  constructor(private tiendaService: TiendaService) {}

  ngOnInit(): void {
    this.cargarMetricas();
  }

  cargarMetricas(): void {
    this.loading = true;
    this.tiendaService.getDashboardMetrics().subscribe({
      next: (data) => {
        this.metrics = data;
        this.loading = false;
        // Esperar a que la vista se renderice antes de crear el gráfico
        setTimeout(() => {
          this.createChart();
        }, 0);
      },
      error: (err) => {
        this.error = 'No se pudieron cargar las métricas. Verifica tu conexión o intenta más tarde.';
        this.loading = false;
        console.error('Error cargando métricas del dashboard:', err);
      }
    });
  }

  createChart() {
    if (!this.metrics || !this.ventasChart) return;
    
    const labels = this.metrics.grafico_ventas.map(v => v.fecha);
    const data = this.metrics.grafico_ventas.map(v => v.cantidad);

    this.chart = new Chart(this.ventasChart.nativeElement, {
      type: 'bar', // Gráfico de barras
      data: {
        labels: labels,
        datasets: [{
          label: 'Productos Vendidos',
          data: data,
          backgroundColor: 'rgba(200, 16, 46, 0.8)', // Usando el rojo Kantu Market
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
  }
}
