import { DatePipe } from '@angular/common';
import { Component, OnInit } from '@angular/core';

import { CallVolumeChartComponent } from './call-volume-chart.component';
import { DashboardService } from './dashboard.service';
import { StatTileComponent } from './stat-tile.component';

@Component({
  selector: 'app-dashboard',
  imports: [StatTileComponent, CallVolumeChartComponent, DatePipe],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
})
export class DashboardComponent implements OnInit {
  constructor(protected readonly dashboard: DashboardService) {}

  ngOnInit(): void {
    this.dashboard.refresh();
  }

  avgHandleTimeMinutes(seconds: number | null): number {
    return seconds ? Math.round((seconds / 60) * 10) / 10 : 0;
  }
}
