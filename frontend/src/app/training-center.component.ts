import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';

import { InsightCategory, InsightStatus, TrainingService } from './training.service';

const CATEGORY_LABELS: Record<InsightCategory, string> = {
  missing_knowledge: 'Missing knowledge',
  prompt_improvement: 'Prompt improvement',
  workflow_improvement: 'Workflow improvement',
};

@Component({
  selector: 'app-training-center',
  imports: [DatePipe],
  templateUrl: './training-center.component.html',
  styleUrl: './training-center.component.css',
})
export class TrainingCenterComponent implements OnInit {
  statusFilter = signal<InsightStatus | 'all'>('all');

  readonly filteredInsights = computed(() => {
    const filter = this.statusFilter();
    const insights = this.training.insights();
    return filter === 'all' ? insights : insights.filter((i) => i.status === filter);
  });

  constructor(protected readonly training: TrainingService) {}

  ngOnInit(): void {
    this.training.refresh();
  }

  categoryLabel(category: InsightCategory): string {
    return CATEGORY_LABELS[category] ?? category;
  }

  onAcknowledge(id: string): void {
    this.training.updateStatus(id, 'acknowledged');
  }

  onDismiss(id: string): void {
    this.training.updateStatus(id, 'dismissed');
  }
}
