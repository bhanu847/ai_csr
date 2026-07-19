import { Component, Input, computed, signal } from '@angular/core';

import { IntentCount } from './dashboard.service';

@Component({
  selector: 'app-intent-bar-chart',
  templateUrl: './intent-bar-chart.component.html',
  styleUrl: './intent-bar-chart.component.css',
})
export class IntentBarChartComponent {
  private readonly _data = signal<IntentCount[]>([]);

  @Input({ required: true })
  set data(value: IntentCount[]) {
    this._data.set(value ?? []);
  }
  get data(): IntentCount[] {
    return this._data();
  }

  readonly hovered = signal<string | null>(null);

  readonly maxCount = computed(() => Math.max(1, ...this._data().map((d) => d.count)));

  pct(count: number): number {
    return (count / this.maxCount()) * 100;
  }
}
