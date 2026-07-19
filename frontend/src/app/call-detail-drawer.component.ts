import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, signal } from '@angular/core';

import { Call, CallDetail, CallsService, TranscriptEntry } from './calls.service';
import { formatDuration } from './format-duration';

@Component({
  selector: 'app-call-detail-drawer',
  imports: [DatePipe, DecimalPipe, JsonPipe],
  templateUrl: './call-detail-drawer.component.html',
  styleUrl: './call-detail-drawer.component.css',
})
export class CallDetailDrawerComponent implements OnChanges {
  @Input() call: Call | null = null;
  @Output() readonly closed = new EventEmitter<void>();

  readonly detail = signal<CallDetail | null>(null);
  readonly transcript = signal<TranscriptEntry[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private readonly calls: CallsService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['call']) {
      return;
    }
    this.detail.set(null);
    this.transcript.set([]);
    this.error.set(null);
    if (this.call) {
      this.load(this.call.id);
    }
  }

  private async load(callId: string): Promise<void> {
    this.loading.set(true);
    try {
      const [detail, transcript] = await Promise.all([
        this.calls.getDetail(callId),
        this.calls.getTranscript(callId),
      ]);
      this.detail.set(detail);
      this.transcript.set(transcript);
    } catch {
      this.error.set('Could not load call transcript.');
    } finally {
      this.loading.set(false);
    }
  }

  duration(call: Call): string {
    return formatDuration(call.started_at, call.ended_at);
  }
}
