import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-stat-tile',
  templateUrl: './stat-tile.component.html',
  styleUrl: './stat-tile.component.css',
})
export class StatTileComponent {
  @Input({ required: true }) label!: string;
  @Input({ required: true }) value!: number;
  @Input() accent: 'accent' | 'good' | 'warning' = 'accent';

  get formattedValue(): string {
    return this.value >= 10000
      ? Intl.NumberFormat('en', { notation: 'compact' }).format(this.value)
      : this.value.toLocaleString('en');
  }
}
