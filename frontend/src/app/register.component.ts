import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from './auth.service';

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
      await this.router.navigateByUrl('/agents');
    } catch {
      this.error.set('Could not create workspace — slug may already be taken.');
    } finally {
      this.submitting.set(false);
    }
  }
}
