import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-password-recovery',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './password-recovery.component.html',
  styleUrls: ['./password-recovery.component.css']
})
export class PasswordRecoveryComponent {
  requestForm: FormGroup;
  resetForm: FormGroup;
  mode: 'request' | 'reset' = 'request';
  message = '';
  errorMessage = '';
  loading = false;
  resetSuccess = false;
  showPassword = false;
  showPasswordConfirm = false;
  uid = '';
  token = '';

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private route: ActivatedRoute
  ) {
    this.requestForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]]
    });

    this.resetForm = this.fb.group({
      new_password: ['', [Validators.required, this.passwordComplexityValidator]],
      new_password_confirm: ['', [Validators.required]]
    }, { validators: this.passwordMatchValidator });

    // Detectar si estamos en modo "reset" por parámetros de ruta
    this.route.params.subscribe(params => {
      if (params['uid'] && params['token']) {
        this.mode = 'reset';
        this.uid = params['uid'];
        this.token = params['token'];
      }
    });
  }

  togglePasswordVisibility(): void {
    this.showPassword = !this.showPassword;
  }

  togglePasswordConfirmVisibility(): void {
    this.showPasswordConfirm = !this.showPasswordConfirm;
  }

  passwordComplexityValidator(control: AbstractControl): ValidationErrors | null {
    const value = control.value || '';
    if (!value) return null;

    const hasMinLength = value.length >= 8;
    const hasLetter = /[a-zA-Z]/.test(value);
    const hasNumber = /[0-9]/.test(value);
    const hasSpecial = /[^a-zA-Z0-9]/.test(value);

    const errors: ValidationErrors = {};
    if (!hasMinLength) errors['minLength'] = true;
    if (!hasLetter) errors['missingLetter'] = true;
    if (!hasNumber) errors['missingNumber'] = true;
    if (!hasSpecial) errors['missingSpecial'] = true;

    return Object.keys(errors).length > 0 ? errors : null;
  }

  passwordMatchValidator(control: AbstractControl): ValidationErrors | null {
    const password = control.get('new_password');
    const confirm = control.get('new_password_confirm');
    if (password && confirm && password.value && confirm.value && password.value !== confirm.value) {
      return { passwordMismatch: true };
    }
    return null;
  }

  // Helpers para la guía visual de requisitos en tiempo real
  get hasMinLength(): boolean {
    return (this.resetForm.get('new_password')?.value || '').length >= 8;
  }

  get hasLetter(): boolean {
    return /[a-zA-Z]/.test(this.resetForm.get('new_password')?.value || '');
  }

  get hasNumber(): boolean {
    return /[0-9]/.test(this.resetForm.get('new_password')?.value || '');
  }

  get hasSpecial(): boolean {
    return /[^a-zA-Z0-9]/.test(this.resetForm.get('new_password')?.value || '');
  }

  onRequestSubmit(): void {
    if (this.requestForm.invalid) return;

    this.loading = true;
    this.message = '';
    this.errorMessage = '';

    this.authService.requestPasswordReset(this.requestForm.value.email).subscribe({
      next: (res) => {
        this.loading = false;
        this.message = res.mensaje || 'Si el correo existe, recibirás un enlace de recuperación.';
      },
      error: (err) => {
        this.loading = false;
        if (err.error && typeof err.error === 'object') {
          const messages = Object.values(err.error).flat();
          this.errorMessage = (messages as string[]).join(' ');
        } else {
          this.errorMessage = 'Error al procesar la solicitud. Intenta de nuevo.';
        }
      }
    });
  }

  onResetSubmit(): void {
    if (this.resetForm.invalid) return;

    const { new_password, new_password_confirm } = this.resetForm.value;
    if (new_password !== new_password_confirm) {
      this.errorMessage = 'Las contraseñas no coinciden.';
      return;
    }

    this.loading = true;
    this.message = '';
    this.errorMessage = '';

    this.authService.confirmPasswordReset(this.uid, this.token, new_password, new_password_confirm).subscribe({
      next: (res) => {
        this.loading = false;
        this.resetSuccess = true;
        this.message = res.mensaje || 'Contraseña restablecida exitosamente. Ya puedes iniciar sesión.';
        this.resetForm.reset();
      },
      error: (err) => {
        this.loading = false;
        if (err.error && typeof err.error === 'object') {
          const messages = Object.values(err.error).flat();
          this.errorMessage = (messages as string[]).join(' ');
        } else {
          this.errorMessage = 'Error al restablecer la contraseña. El enlace puede haber expirado o ser inválido.';
        }
      }
    });
  }
}
