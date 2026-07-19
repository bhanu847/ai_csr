import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from './auth.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './auth-form.css',
})
export class LoginComponent {
  tenantSlug = '';
  email = '';
  password = '';
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
      await this.auth.login(this.tenantSlug, this.email, this.password);
      await this.router.navigateByUrl('/agents');
    } catch {
      this.error.set('Invalid workspace, email, or password.');
    } finally {
      this.submitting.set(false);
    }
  }
}
