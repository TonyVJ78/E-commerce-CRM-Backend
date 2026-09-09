import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TiendaService, Tienda } from '../../../core/services/tienda.service';

@Component({
  selector: 'app-create-tienda',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './create-tienda.component.html',
  styleUrls: ['./create-tienda.component.css']
})
export class CreateTiendaComponent implements OnInit {
  tiendaForm: FormGroup;
  tiendas: Tienda[] = [];
  message = '';
  errorMessage = '';
  loading = false;
  showForm = false;

  constructor(
    private fb: FormBuilder,
    private tiendaService: TiendaService
  ) {
    this.tiendaForm = this.fb.group({
      nombre: ['', [Validators.required, Validators.maxLength(150)]],
      slug: ['', [Validators.maxLength(100)]],
      logo_url: ['', [Validators.maxLength(255)]],
      color_primario: ['#C8102E'],
      descripcion: ['']
    });
  }

  ngOnInit(): void {
    this.loadTiendas();
  }

  loadTiendas(): void {
    this.tiendaService.listar().subscribe({
      next: (data) => this.tiendas = data,
      error: () => {}
    });
  }

  toggleForm(): void {
    this.showForm = !this.showForm;
    this.message = '';
    this.errorMessage = '';
    if (!this.showForm) {
      this.tiendaForm.reset({ color_primario: '#C8102E' });
    }
  }

  onSubmit(): void {
    if (this.tiendaForm.invalid) return;

    this.loading = true;
    this.message = '';
    this.errorMessage = '';

    const formData = { ...this.tiendaForm.value };
    // Limpiar campos vacíos para que el backend use defaults
    if (!formData.slug) delete formData.slug;
    if (!formData.logo_url) delete formData.logo_url;

    this.tiendaService.crear(formData).subscribe({
      next: (tienda) => {
        this.loading = false;
        this.message = `¡Tienda "${tienda.nombre}" creada exitosamente! Slug: ${tienda.slug}`;
        this.tiendas.unshift(tienda);
        this.showForm = false;
        this.tiendaForm.reset({ color_primario: '#C8102E' });
      },
      error: (err) => {
        this.loading = false;
        if (err.error && typeof err.error === 'object') {
          const messages = Object.entries(err.error).map(([k, v]) => `${k}: ${(v as string[]).join(', ')}`);
          this.errorMessage = messages.join(' | ');
        } else {
          this.errorMessage = 'Error al crear la tienda. Intenta de nuevo.';
        }
      }
    });
  }
}
