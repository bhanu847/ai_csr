import { HttpClient } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  role: string;
}

const API_URL = 'http://localhost:8001/api/auth';
const TOKEN_KEY = 'ai_workforce_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly token = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  readonly currentUser = signal<CurrentUser | null>(null);
  readonly isAuthenticated = computed(() => this.token() !== null);

  constructor(private readonly http: HttpClient) {
    if (this.token()) {
      this.loadCurrentUser();
    }
  }

  async registerTenant(
    tenantName: string,
    tenantSlug: string,
    adminEmail: string,
    adminPassword: string,
  ): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ access_token: string }>(`${API_URL}/register-tenant`, {
        tenant_name: tenantName,
        tenant_slug: tenantSlug,
        admin_email: adminEmail,
        admin_password: adminPassword,
      }),
    );
    this.setToken(res.access_token);
    await this.loadCurrentUser();
  }

  async login(tenantSlug: string, email: string, password: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ access_token: string }>(`${API_URL}/login`, {
        tenant_slug: tenantSlug,
        email,
        password,
      }),
    );
    this.setToken(res.access_token);
    await this.loadCurrentUser();
  }

  logout(): void {
    this.token.set(null);
    this.currentUser.set(null);
    localStorage.removeItem(TOKEN_KEY);
  }

  private setToken(token: string): void {
    this.token.set(token);
    localStorage.setItem(TOKEN_KEY, token);
  }

  private async loadCurrentUser(): Promise<void> {
    try {
      const user = await firstValueFrom(this.http.get<CurrentUser>(`${API_URL}/me`));
      this.currentUser.set(user);
    } catch {
      this.logout();
    }
  }
}
