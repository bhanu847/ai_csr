import { Component, signal } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { AuthService } from './auth.service';
import { SidebarComponent } from './sidebar.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, SidebarComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly sidebarCollapsed = signal(false);
  readonly mobileNavOpen = signal(false);

  constructor(
    protected readonly auth: AuthService,
    private readonly router: Router,
  ) {}

  onLogout(): void {
    this.auth.logout();
    this.router.navigateByUrl('/login');
  }
}
