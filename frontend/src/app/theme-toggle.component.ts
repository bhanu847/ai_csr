import { Component, HostBinding, Input } from '@angular/core';

import { ThemeService } from './theme.service';

@Component({
  selector: 'app-theme-toggle',
  templateUrl: './theme-toggle.component.html',
  styleUrl: './theme-toggle.component.css',
})
export class ThemeToggleComponent {
  @Input() @HostBinding('class.collapsed') collapsed = false;

  constructor(protected readonly theme: ThemeService) {}
}
