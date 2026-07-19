import { Component, OnInit } from '@angular/core';

import { CallVolumeChartComponent } from './call-volume-chart.component';
import { DashboardService } from './dashboard.service';
import { IntentBarChartComponent } from './intent-bar-chart.component';
import { ResolutionTrendChartComponent } from './resolution-trend-chart.component';
import { SentimentMixChartComponent } from './sentiment-mix-chart.component';

@Component({
  selector: 'app-analytics',
  imports: [CallVolumeChartComponent, IntentBarChartComponent, SentimentMixChartComponent, ResolutionTrendChartComponent],
  templateUrl: './analytics.component.html',
  styleUrl: './analytics.component.css',
})
export class AnalyticsComponent implements OnInit {
  constructor(protected readonly dashboard: DashboardService) {}

  ngOnInit(): void {
    this.dashboard.refresh();
    this.dashboard.refreshAnalytics();
  }
}
