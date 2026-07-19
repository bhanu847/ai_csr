import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from './auth.service';
import { ThemeToggleComponent } from './theme-toggle.component';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive, ThemeToggleComponent],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css',
})
export class SidebarComponent {
  @Input() collapsed = false;
  @Input() mobileOpen = false;
  @Output() readonly collapsedChange = new EventEmitter<boolean>();
  @Output() readonly closeMobile = new EventEmitter<void>();
  @Output() readonly logout = new EventEmitter<void>();

  constructor(protected readonly auth: AuthService) {}

  initials(email: string | undefined): string {
    if (!email) return '?';
    return email.charAt(0).toUpperCase();
  }
}
