import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';

import { FeedbackService, LearnedAnswer } from './feedback.service';
import { InsightCategory, InsightStatus, TrainingService } from './training.service';

const ORIGIN_LABELS: Record<LearnedAnswer['origin'], string> = {
  correction: 'Reviewer correction',
  regenerated: 'Re-answered from documents',
  confirmed: 'Confirmed by reviewer',
  unanswered: 'Not in documents — always uses full AI',
};

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

  constructor(
    protected readonly training: TrainingService,
    protected readonly feedback: FeedbackService,
  ) {}

  ngOnInit(): void {
    this.training.refresh();
    this.feedback.refreshLearned();
  }

  originLabel(origin: LearnedAnswer['origin']): string {
    return ORIGIN_LABELS[origin] ?? origin;
  }

  onToggleLearned(answer: LearnedAnswer): void {
    this.feedback.setActive(answer.id, !answer.active);
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
