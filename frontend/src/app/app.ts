import { Component } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';

import { AuthService } from './auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  constructor(
    protected readonly auth: AuthService,
    private readonly router: Router,
  ) {}

  onLogout(): void {
    this.auth.logout();
    this.router.navigateByUrl('/login');
  }
}
