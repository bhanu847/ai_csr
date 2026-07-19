import { Component, ElementRef, Input, ViewChild, computed, signal } from '@angular/core';

import { CallVolumePoint } from './dashboard.service';

const WIDTH = 640;
const HEIGHT = 220;
const PAD_LEFT = 36;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;

interface PlottedPoint extends CallVolumePoint {
  x: number;
  y: number;
}

@Component({
  selector: 'app-call-volume-chart',
  templateUrl: './call-volume-chart.component.html',
  styleUrl: './call-volume-chart.component.css',
})
export class CallVolumeChartComponent {
  private readonly _data = signal<CallVolumePoint[]>([]);

  @Input({ required: true })
  set data(value: CallVolumePoint[]) {
    this._data.set(value ?? []);
  }
  get data(): CallVolumePoint[] {
    return this._data();
  }

  readonly showTable = signal(false);
  readonly hoverIndex = signal<number | null>(null);

  readonly width = WIDTH;
  readonly height = HEIGHT;
  readonly baselineY = HEIGHT - PAD_BOTTOM;

  readonly maxValue = computed(() => {
    const max = Math.max(1, ...this._data().map((d) => d.count));
    const magnitude = Math.pow(10, Math.floor(Math.log10(max)));
    return Math.max(magnitude, Math.ceil(max / magnitude) * magnitude);
  });

  readonly points = computed<PlottedPoint[]>(() => {
    const data = this._data();
    const n = data.length;
    if (n === 0) return [];
    const innerWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    const max = this.maxValue();
    return data.map((d, i) => ({
      ...d,
      x: n === 1 ? PAD_LEFT : PAD_LEFT + (innerWidth * i) / (n - 1),
      y: PAD_TOP + innerHeight * (1 - d.count / max),
    }));
  });

  readonly linePath = computed(() => {
    const pts = this.points();
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  });

  readonly areaPath = computed(() => {
    const pts = this.points();
    if (pts.length === 0) return '';
    const first = pts[0];
    const last = pts[pts.length - 1];
    const body = pts.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
    return `M ${first.x.toFixed(1)} ${this.baselineY} ${body} L ${last.x.toFixed(1)} ${this.baselineY} Z`;
  });

  readonly gridLines = computed(() => {
    const max = this.maxValue();
    const steps = 4;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    return Array.from({ length: steps + 1 }, (_, i) => ({
      value: Math.round((max * (steps - i)) / steps),
      y: PAD_TOP + (innerHeight * i) / steps,
    }));
  });

  readonly xTicks = computed(() => {
    const pts = this.points();
    const n = pts.length;
    if (n === 0) return [];
    const idxs = n <= 5 ? pts.map((_, i) => i) : [0, Math.floor((n - 1) / 2), n - 1];
    return idxs.map((i) => pts[i]);
  });

  readonly hovered = computed(() => {
    const idx = this.hoverIndex();
    return idx === null ? null : this.points()[idx];
  });

  readonly tooltipX = computed(() => {
    const p = this.hovered();
    if (!p) return 0;
    return Math.min(Math.max(p.x - 42, PAD_LEFT), WIDTH - PAD_RIGHT - 84);
  });

  readonly tooltipY = computed(() => {
    const p = this.hovered();
    if (!p) return 0;
    return p.y > 60 ? p.y - 48 : p.y + 14;
  });

  @ViewChild('svgEl') private svgRef?: ElementRef<SVGSVGElement>;

  onPointerMove(event: PointerEvent): void {
    const pts = this.points();
    if (pts.length === 0 || !this.svgRef) return;
    const rect = this.svgRef.nativeElement.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const localX = (event.clientX - rect.left) * scaleX;
    let closest = 0;
    let closestDist = Infinity;
    pts.forEach((p, i) => {
      const dist = Math.abs(p.x - localX);
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
