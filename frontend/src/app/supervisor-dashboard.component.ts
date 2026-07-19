import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { CallDetailDrawerComponent } from './call-detail-drawer.component';
import { LiveCall, SupervisorService } from './supervisor.service';

const POLL_INTERVAL_MS = 4000;

@Component({
  selector: 'app-supervisor-dashboard',
  imports: [FormsModule, CallDetailDrawerComponent],
  templateUrl: './supervisor-dashboard.component.html',
  styleUrl: './supervisor-dashboard.component.css',
})
export class SupervisorDashboardComponent implements OnInit, OnDestroy {
  private pollHandle?: ReturnType<typeof setInterval>;

  readonly monitoredCall = signal<LiveCall | null>(null);
  readonly suggestingCallId = signal<string | null>(null);
  readonly pendingAction = signal<string | null>(null);
  suggestionText = '';

  constructor(protected readonly supervisor: SupervisorService) {}

  ngOnInit(): void {
    this.supervisor.refresh();
    this.pollHandle = setInterval(async () => {
      await this.supervisor.refresh();
      // Keep the open monitor drawer fresh — a new object reference from
      // this poll re-triggers the drawer's own reload via its ngOnChanges.
      const monitored = this.monitoredCall();
      if (monitored) {
        const fresh = this.supervisor.liveCalls().find((c) => c.id === monitored.id) ?? null;
        this.monitoredCall.set(fresh);
      }
    }, POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
    }
  }

  onMonitor(call: LiveCall): void {
    this.monitoredCall.set(call);
  }

  async onPauseToggle(call: LiveCall): Promise<void> {
    this.pendingAction.set(call.id);
    try {
      if (call.ai_paused) {
        await this.supervisor.resume(call.id);
      } else {
        await this.supervisor.pause(call.id);
      }
    } finally {
      this.pendingAction.set(null);
    }
  }

  onOpenSuggestionBox(callId: string): void {
    this.suggestingCallId.set(callId);
    this.suggestionText = '';
  }

  onCancelSuggestion(): void {
    this.suggestingCallId.set(null);
  }

  async onSendSuggestion(callId: string): Promise<void> {
    if (!this.suggestionText.trim()) return;
    this.pendingAction.set(callId);
    try {
      await this.supervisor.sendSuggestion(callId, this.suggestionText);
      this.suggestingCallId.set(null);
    } finally {
      this.pendingAction.set(null);
    }
  }

  confidenceBand(confidence: number | null): 'good' | 'warning' | 'critical' | null {
    if (confidence === null) return null;
    if (confidence >= 90) return 'good';
    if (confidence >= 70) return 'warning';
    return 'critical';
  }
}
