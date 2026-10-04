import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, inject, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import {
  Tienda,
  TiendaIdentidad,
  TiendaService
} from '../../../core/services/tienda.service';

type SlugStatus = 'checking' | 'available' | 'occupied' | null;

@Component({
  selector: 'app-identidad-marca',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './identidad-marca.component.html',
  styleUrls: ['./identidad-marca.component.css']
})
export class IdentidadMarcaComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly tiendaService = inject(TiendaService);

  readonly maxLogoBytes = 5 * 1024 * 1024; // 5 MB
  readonly identityForm = this.fb.nonNullable.group({
    slug: ['', [
      Validators.required,
      Validators.maxLength(100),
      Validators.pattern(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
    ]],
    color_primario: ['#C8102E', [
      Validators.required,
      Validators.pattern(/^#[0-9A-Fa-f]{6}$/)
    ]]
  });

  tiendas: Tienda[] = [];
  selectedStoreId: number | null = null;
  identidad: TiendaIdentidad | null = null;
  selectedLogo: File | null = null;
  logoPreviewUrl: string | null = null;
  slugStatus: SlugStatus = null;

  loadingStores = true;
  loadingIdentity = false;
  saving = false;
  successMessage = '';
  errorMessage = '';
  logoError = '';

  @ViewChild('logoInput') logoInput?: ElementRef<HTMLInputElement>;

  constructor() {
    this.identityForm.disable();
  }

  ngOnInit(): void {
    this.loadStores();
  }

  ngOnDestroy(): void {
    this.revokeLogoPreview();
  }

  get slugControl() {
    return this.identityForm.controls.slug;
  }

  get colorControl() {
    return this.identityForm.controls.color_primario;
  }

  loadStores(): void {
    this.loadingStores = true;
    this.errorMessage = '';
    this.tiendaService.listar().subscribe({
      next: stores => {
        this.tiendas = stores;
        this.loadingStores = false;

        if (stores.length === 1) {
          const onlyStore = stores.at(0);
          if (onlyStore) {
            this.selectStore(onlyStore.id);
          }
        }
      },
      error: error => {
        this.loadingStores = false;
        this.errorMessage = this.readHttpError(
          error,
          'No pudimos cargar tus tiendas. Intenta nuevamente.'
        );
      }
    });
  }

  onStoreChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    const storeId = Number(value);
    if (!value || !Number.isInteger(storeId) || storeId <= 0) {
      this.clearStoreSelection();
      return;
    }
    this.selectStore(storeId);
  }

  selectStore(storeId: number): void {
    if (!this.tiendas.some(store => store.id === storeId)) {
      this.clearStoreSelection();
      return;
    }

    this.selectedStoreId = storeId;
    this.identidad = null;
    this.slugStatus = null;
    this.successMessage = '';
    this.errorMessage = '';
    this.logoError = '';
    this.selectedLogo = null;
    this.revokeLogoPreview();
    this.resetLogoInput();
    this.identityForm.disable();
    this.loadingIdentity = true;

    this.tiendaService.obtenerIdentidad(storeId).subscribe({
      next: identity => {
        this.identidad = identity;
        this.identityForm.reset({
          slug: identity.slug,
          color_primario: identity.color_primario
        });
        this.identityForm.enable();
        this.loadingIdentity = false;
      },
      error: error => {
        this.loadingIdentity = false;
        this.errorMessage = this.readHttpError(
          error,
          'No pudimos cargar la identidad de esta tienda.'
        );
      }
    });
  }

  onSlugBlur(): void {
    if (!this.selectedStoreId) {
      return;
    }

    const normalized = this.normalizeSlug(this.slugControl.value);
    this.slugControl.setValue(normalized);
    this.slugControl.markAsTouched();
    this.slugStatus = null;

    if (this.slugControl.invalid) {
      return;
    }

    this.slugStatus = 'checking';
    const requestedSlug = normalized;
    this.tiendaService.verificarSlug(this.selectedStoreId, normalized).subscribe({
      next: result => {
        if (this.slugControl.value !== requestedSlug) {
          return;
        }
        this.slugStatus = result.disponible ? 'available' : 'occupied';
      },
      error: error => {
        this.slugStatus = null;
        this.errorMessage = this.readHttpError(
          error,
          'No fue posible comprobar la disponibilidad del slug.'
        );
      }
    });
  }

  onColorBlur(): void {
    const raw = this.colorControl.value.trim().toUpperCase();
    this.colorControl.setValue(raw);
    this.colorControl.markAsTouched();
  }

  onLogoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.item(0) ?? null;
    this.logoError = '';
    this.selectedLogo = null;
    this.revokeLogoPreview();

    if (!file) {
      return;
    }

    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!allowedTypes.includes(file.type) || !extension || !['jpg', 'jpeg', 'png', 'webp'].includes(extension)) {
      this.logoError = 'Selecciona un archivo JPEG, PNG o WebP.';
      input.value = '';
      return;
    }
    if (file.size > this.maxLogoBytes) {
      this.logoError = 'El logotipo no puede superar los 5 MB.';
      input.value = '';
      return;
    }

    this.selectedLogo = file;
    this.logoPreviewUrl = URL.createObjectURL(file);
    this.successMessage = '';
  }

  save(): void {
    if (!this.selectedStoreId || this.identityForm.invalid || this.saving) {
      this.identityForm.markAllAsTouched();
      return;
    }
    if (this.slugStatus === 'occupied') {
      this.errorMessage = 'El slug elegido ya está en uso.';
      return;
    }

    this.saving = true;
    this.successMessage = '';
    this.errorMessage = '';
    const data = this.identityForm.getRawValue();

    this.tiendaService.actualizarIdentidad(
      this.selectedStoreId,
      data,
      this.selectedLogo ?? undefined
    ).subscribe({
      next: identity => {
        this.identidad = identity;
        this.tiendas = this.tiendas.map(store => store.id === identity.id
          ? {
              ...store,
              slug: identity.slug,
              logo_url: identity.logo_url,
              color_primario: identity.color_primario
            }
          : store
        );
        this.identityForm.reset({
          slug: identity.slug,
          color_primario: identity.color_primario
        });
        this.selectedLogo = null;
        this.revokeLogoPreview();
        this.resetLogoInput();
        this.slugStatus = 'available';
        this.saving = false;
        this.successMessage = 'La identidad de marca se guardó correctamente.';
      },
      error: error => {
        this.saving = false;
        this.errorMessage = this.readHttpError(
          error,
          'No pudimos guardar los cambios. Intenta nuevamente.'
        );
      }
    });
  }

  private clearStoreSelection(): void {
    this.selectedStoreId = null;
    this.identidad = null;
    this.slugStatus = null;
    this.selectedLogo = null;
    this.revokeLogoPreview();
    this.resetLogoInput();
    this.identityForm.reset({slug: '', color_primario: '#C8102E'});
    this.identityForm.disable();
  }

  private normalizeSlug(value: string): string {
    return value
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 100);
  }

  private revokeLogoPreview(): void {
    if (this.logoPreviewUrl) {
      URL.revokeObjectURL(this.logoPreviewUrl);
      this.logoPreviewUrl = null;
    }
  }

  private resetLogoInput(): void {
    if (this.logoInput) {
      this.logoInput.nativeElement.value = '';
    }
  }

  private readHttpError(error: unknown, fallback: string): string {
    if (!(error instanceof HttpErrorResponse)) {
      return fallback;
    }

    // Regla CU-13: procesar adecuadamente error 403 de violación multitenant
    if (error.status === 403) {
      return 'No tienes permisos de propietario para modificar esta tienda (acceso denegado multitenant).';
    }

    const body: unknown = error.error;
    if (typeof body === 'string' && body.trim()) {
      return body;
    }
    if (!body || typeof body !== 'object') {
      return fallback;
    }

    const entries = Object.entries(body as Record<string, unknown>);
    const messages = entries.flatMap(([field, value]) => {
      const labels: Record<string, string> = {
        slug: 'Slug',
        color_primario: 'Color principal',
        logo: 'Logotipo'
      };
      const label = field === 'detail' ? '' : `${labels[field] ?? field}: `;
      if (Array.isArray(value)) {
        return value.map(item => `${label}${String(item)}`);
      }
      if (typeof value === 'string') {
        return [`${label}${value}`];
      }
      return [];
    });
    return messages.length ? messages.join(' ') : fallback;
  }
}
