import { Component, ElementRef, Input, ViewChild, computed, signal } from '@angular/core';

import { ResolutionTrendPoint } from './dashboard.service';

const WIDTH = 640;
const HEIGHT = 220;
const PAD_LEFT = 36;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;
const BAR_MAX_WIDTH = 24;
const SEG_GAP = 2;

type SegKey = 'resolved' | 'escalated' | 'abandoned';
const SEG_ORDER: SegKey[] = ['resolved', 'escalated', 'abandoned'];

interface SegRect {
  key: SegKey;
  y: number;
  height: number;
}

interface DayBar extends ResolutionTrendPoint {
  x: number;
  barWidth: number;
  total: number;
  segRects: SegRect[];
}

@Component({
  selector: 'app-resolution-trend-chart',
  templateUrl: './resolution-trend-chart.component.html',
  styleUrl: './resolution-trend-chart.component.css',
})
export class ResolutionTrendChartComponent {
  private readonly _data = signal<ResolutionTrendPoint[]>([]);

  @Input({ required: true })
  set data(value: ResolutionTrendPoint[]) {
    this._data.set(value ?? []);
  }

  readonly showTable = signal(false);
  readonly hoverIndex = signal<number | null>(null);

  readonly width = WIDTH;
  readonly height = HEIGHT;
  readonly baselineY = HEIGHT - PAD_BOTTOM;

  readonly maxTotal = computed(() => {
    const max = Math.max(1, ...this._data().map((d) => d.resolved + d.escalated + d.abandoned));
    const magnitude = Math.pow(10, Math.floor(Math.log10(max)));
    return Math.max(magnitude, Math.ceil(max / magnitude) * magnitude);
  });

  readonly bars = computed<DayBar[]>(() => {
    const data = this._data();
    const n = data.length;
    if (n === 0) return [];
    const innerWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    const max = this.maxTotal();
    const slotWidth = innerWidth / n;
    const barWidth = Math.min(BAR_MAX_WIDTH, slotWidth * 0.6);

    return data.map((d, i) => {
      const total = d.resolved + d.escalated + d.abandoned;
      const x = PAD_LEFT + slotWidth * i + slotWidth / 2;

      let cursor = this.baselineY;
      const segRects: SegRect[] = [];
      for (const key of SEG_ORDER) {
        const value = d[key];
        if (value <= 0) continue;
        const rawHeight = (value / max) * innerHeight;
        segRects.push({ key, y: cursor - rawHeight + SEG_GAP / 2, height: Math.max(0, rawHeight - SEG_GAP) });
        cursor -= rawHeight;
      }

      return { ...d, x, barWidth, total, segRects };
    });
  });

  readonly gridLines = computed(() => {
    const max = this.maxTotal();
    const steps = 4;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    return Array.from({ length: steps + 1 }, (_, i) => ({
      value: Math.round((max * (steps - i)) / steps),
      y: PAD_TOP + (innerHeight * i) / steps,
    }));
  });

  readonly xTicks = computed(() => {
    const bars = this.bars();
    const n = bars.length;
    if (n === 0) return [];
    const idxs = n <= 5 ? bars.map((_, i) => i) : [0, Math.floor((n - 1) / 2), n - 1];
    return idxs.map((i) => bars[i]);
  });

  readonly hovered = computed(() => {
    const idx = this.hoverIndex();
    return idx === null ? null : this.bars()[idx];
  });

  readonly tooltipX = computed(() => {
    const b = this.hovered();
    if (!b) return 0;
    return Math.min(Math.max(b.x - 50, PAD_LEFT), WIDTH - PAD_RIGHT - 100);
  });

  @ViewChild('svgEl') private svgRef?: ElementRef<SVGSVGElement>;

  onPointerMove(event: PointerEvent): void {
    const bars = this.bars();
    if (bars.length === 0 || !this.svgRef) return;
    const rect = this.svgRef.nativeElement.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const localX = (event.clientX - rect.left) * scaleX;
    let closest = 0;
    let closestDist = Infinity;
    bars.forEach((b, i) => {
      const dist = Math.abs(b.x - localX);
      if (dist < closestDist) {
        closestDist = dist;
        closest = i;
      }
    });
    this.hoverIndex.set(closest);
  }

  onPointerLeave(): void {
    this.hoverIndex.set(null);
  }

  formatDate(iso: string): string {
    return new Date(iso + 'T00:00:00').toLocaleDateString('en', { month: 'short', day: 'numeric' });
  }
}
