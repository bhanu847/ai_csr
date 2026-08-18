import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from './auth.service';

function extractErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg ?? JSON.stringify(d)).join('; ');
    }
    if (err.status === 409) return 'That workspace slug is already taken.';
  }
  return 'Could not create workspace. Please try again.';
}

@Component({
  selector: 'app-register',
  imports: [FormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './auth-form.css',
})
export class RegisterComponent {
  tenantName = '';
  tenantSlug = '';
  adminEmail = '';
  adminPassword = '';
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);

  constructor(
    private readonly auth: AuthService,
    private readonly router: Router,
  ) {}

  async onSubmit(): Promise<void> {
    this.submitting.set(true);
    this.error.set(null);
    try {
      await this.auth.registerTenant(
        this.tenantName,
        this.tenantSlug,
        this.adminEmail,
        this.adminPassword,
      );
      await this.router.navigateByUrl('/dashboard');
    } catch (err) {
      this.error.set(extractErrorMessage(err));
    } finally {
      this.submitting.set(false);
    }
  }
}
