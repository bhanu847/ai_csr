import { DecimalPipe } from '@angular/common';
import { Component, Input, computed, signal } from '@angular/core';

import { SentimentCount } from './dashboard.service';

const LABELS: Record<string, string> = {
  positive: 'Positive',
  neutral: 'Neutral',
  negative: 'Negative',
  frustrated: 'Frustrated',
};

// Sentiment is a good→bad state axis, not a nominal category, so it wears
// status tokens (reserved meaning) rather than the categorical palette.
const ORDER = ['positive', 'neutral', 'negative', 'frustrated'];

interface Segment {
  key: string;
  label: string;
  count: number;
  pct: number;
}

@Component({
  selector: 'app-sentiment-mix-chart',
  imports: [DecimalPipe],
  templateUrl: './sentiment-mix-chart.component.html',
  styleUrl: './sentiment-mix-chart.component.css',
})
export class SentimentMixChartComponent {
  private readonly _data = signal<SentimentCount[]>([]);

  @Input({ required: true })
  set data(value: SentimentCount[]) {
    this._data.set(value ?? []);
  }

  readonly hovered = signal<string | null>(null);

  readonly total = computed(() => this._data().reduce((sum, d) => sum + d.count, 0));

  readonly segments = computed<Segment[]>(() => {
    const total = this.total();
    if (total === 0) return [];
    const byKey = new Map(this._data().map((d) => [d.sentiment, d.count]));
    return ORDER.filter((key) => byKey.has(key)).map((key) => {
      const count = byKey.get(key) ?? 0;
      return { key, label: LABELS[key] ?? key, count, pct: (count / total) * 100 };
    });
  });
}
