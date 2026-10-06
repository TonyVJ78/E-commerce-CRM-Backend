import { Component, OnInit, ElementRef, ViewChild, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TiendaService, DashboardMetrics, VentaDia } from '../../../core/services/tienda.service';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-dashboard-empresa',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard-empresa.component.html',
  styleUrls: ['./dashboard-empresa.component.css']
})
export class DashboardEmpresaComponent implements OnInit {
  private readonly tiendaService = inject(TiendaService);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly metrics = signal<DashboardMetrics | null>(null);
  readonly usarFallback = signal(false);

  private chartInstance: Chart | null = null;
  @ViewChild('ventasChart') ventasChart?: ElementRef<HTMLCanvasElement>;

  readonly ventasSemana = computed<VentaDia[]>(() => {
    const m = this.metrics();
    if (!m) return [];
    const lista = (m as any).grafico_ventas || (m as any).ventas_semana;
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
  });

  readonly maxVentaSemana = computed<number>(() => {
    const vals = this.ventasSemana().map(v => v.cantidad || 0);
    const max = Math.max(...vals, 0);
    return max > 0 ? max : 1;
  });

  readonly totalVentasSemana = computed<number>(() => {
    return this.ventasSemana().reduce((sum, v) => sum + (v.cantidad || 0), 0);
  });

  readonly mejorDia = computed<string>(() => {
    const list = this.ventasSemana();
    if (!list.length) return '';
    let top = list[0];
    for (const d of list) {
      if ((d.cantidad || 0) > (top.cantidad || 0)) {
        top = d;
      }
    }
    return top.cantidad > 0 ? top.fecha : '';
  });

  ngOnInit(): void {
    this.cargarMetricas();
  }

  cargarMetricas(): void {
    this.loading.set(true);
    this.error.set(null);
    this.tiendaService.getDashboardMetrics().subscribe({
      next: (data) => {
        this.metrics.set(data);
        this.loading.set(false);
        setTimeout(() => this.inicializarGrafico(), 0);
      },
      error: (err) => {
        this.error.set('No se pudieron cargar las metricas. Verifica tu conexion o intenta mas tarde.');
        this.loading.set(false);
        console.error('Error cargando metricas del dashboard:', err);
      }
    });
  }

  private inicializarGrafico(): void {
    if (!this.ventasChart?.nativeElement) {
      this.usarFallback.set(true);
      return;
    }

    try {
      if (this.chartInstance) {
        this.chartInstance.destroy();
        this.chartInstance = null;
      }

      const ventas = this.ventasSemana();
      const labels = ventas.map(v => v.fecha);
      const data = ventas.map(v => v.cantidad || 0);
      const maxVal = this.maxVentaSemana();

      const backgroundColors = data.map(val => (val === maxVal && val > 0) ? '#F5B301' : '#C8102E');

      this.chartInstance = new Chart(this.ventasChart.nativeElement, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Productos Vendidos',
            data: data,
            backgroundColor: backgroundColors,
            borderRadius: 6,
            borderSkipped: false
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `Vendidos: ${ctx.parsed.y} unidades`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: '#5F6675', font: { family: 'Inter', weight: 600 } }
            },
            y: {
              beginAtZero: true,
              grid: { color: '#E6E8EE' },
              ticks: { stepSize: 1, color: '#5F6675', font: { family: 'Inter' } }
            }
          }
        }
      });
      this.usarFallback.set(false);
    } catch (err) {
      console.warn('Error inicializando Chart.js, activando fallback visual CSS:', err);
      this.usarFallback.set(true);
    }
  }
}
