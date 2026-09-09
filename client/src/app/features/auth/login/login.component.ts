import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent {
  loginForm: FormGroup;
  errorMessage = '';
  loading = false;
  showPassword = false;

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required]]
    });
  }

  togglePasswordVisibility(): void {
    this.showPassword = !this.showPassword;
  }

  onSubmit(): void {
    if (this.loginForm.invalid) return;

    this.loading = true;
    this.errorMessage = '';

    const { email, password } = this.loginForm.value;
    this.authService.login(email, password).subscribe({
      next: (res) => {
        const rol = res.usuario?.rol;
        if (rol === 'cliente') {
          this.router.navigate(['/inicio']);
        } else if (rol === 'administrador') {
          this.router.navigate(['/dashboard']);
        } else {
          this.router.navigate(['/perfil']);
        }
      },
      error: (err) => {
        this.loading = false;
        const apiError = err.error?.error;
        if (typeof apiError === 'string') {
          this.errorMessage = apiError;
        } else if (apiError?.message && typeof apiError.message === 'string') {
          this.errorMessage = apiError.message;
        } else if (typeof err.error?.detail === 'string') {
          this.errorMessage = err.error.detail;
        } else if (typeof err.error?.message === 'string') {
          this.errorMessage = err.error.message;
        } else {
          this.errorMessage = 'Error al iniciar sesión. Verifica tus credenciales.';
        }
      }
    });
  }
}
