import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, signal } from '@angular/core';

import { Call, CallDetail, CallsService, TranscriptEntry } from './calls.service';
import { FeedbackService } from './feedback.service';
import { formatDuration } from './format-duration';

interface FeedbackState {
  status: 'idle' | 'correcting' | 'saving' | 'done' | 'error';
  helpful?: boolean;
  correction: string;
  message?: string;
  learnedAnswer?: string | null;
}

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
  /** Per assistant-message feedback UI state, keyed by message id. */
  readonly feedback = signal<Record<string, FeedbackState>>({});

  constructor(
    private readonly calls: CallsService,
    private readonly feedbackService: FeedbackService,
  ) {}

  feedbackFor(messageId: string): FeedbackState {
    return this.feedback()[messageId] ?? { status: 'idle', correction: '' };
  }

  private setFeedback(messageId: string, patch: Partial<FeedbackState>): void {
    this.feedback.update((all) => ({ ...all, [messageId]: { ...this.feedbackFor(messageId), ...patch } }));
  }

  startCorrection(messageId: string): void {
    this.setFeedback(messageId, { status: 'correcting' });
  }

  cancelCorrection(messageId: string): void {
    this.setFeedback(messageId, { status: 'idle', correction: '' });
  }

  updateCorrection(messageId: string, value: string): void {
    this.setFeedback(messageId, { correction: value });
  }

  async rate(messageId: string, helpful: boolean): Promise<void> {
    const correction = helpful ? undefined : this.feedbackFor(messageId).correction;
    this.setFeedback(messageId, { status: 'saving', helpful });
    try {
      const result = await this.feedbackService.submit(messageId, helpful, correction);
      this.setFeedback(messageId, {
        status: 'done',
        message: result.message,
        learnedAnswer: result.outcome === 'regenerated' ? result.learned_answer?.answer : null,
      });
    } catch (err) {
      this.setFeedback(messageId, { status: 'error', message: (err as Error).message });
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['call']) {
      return;
    }
    this.detail.set(null);
    this.transcript.set([]);
    this.error.set(null);
    this.feedback.set({});
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

  downloadTranscript(): void {
    const call = this.call;
    if (!call) {
      return;
    }
    const detail = this.detail();
    const entries = this.transcript();

    const lines: string[] = [];
    lines.push('CALL TRANSCRIPT');
    lines.push('='.repeat(60));
    lines.push(`Call SID: ${call.twilio_call_sid}`);
    lines.push(`Agent: ${call.agent_name || 'Unassigned'}`);
    lines.push(`From: ${call.from_number}`);
    lines.push(`To: ${call.to_number}`);
    lines.push(`Status: ${call.status}`);
    lines.push(`Started: ${this.formatTimestamp(call.started_at)}`);
    lines.push(`Ended: ${call.ended_at ? this.formatTimestamp(call.ended_at) : '—'}`);
    lines.push(`Duration: ${this.duration(call)}`);
    if (detail?.intent) {
      lines.push(`Intent: ${detail.intent}`);
    }
    if (detail?.resolution_status) {
      lines.push(`Resolution: ${detail.resolution_status}`);
    }

    lines.push('');
    lines.push('SENTIMENT ANALYSIS');
    lines.push('-'.repeat(60));
    lines.push(`Overall sentiment: ${detail?.sentiment ?? call.sentiment ?? 'Not analyzed'}`);
    if (detail?.confidence_score !== null && detail?.confidence_score !== undefined) {
      lines.push(`AI confidence: ${Math.round(detail.confidence_score)}%`);
    }
    if (detail?.empathy_score !== null && detail?.empathy_score !== undefined) {
      lines.push(`Empathy score: ${Math.round(detail.empathy_score)}%`);
    }

    if (detail?.summary) {
      lines.push('');
      lines.push('SUMMARY');
      lines.push('-'.repeat(60));
      lines.push(detail.summary);
    }

    if (detail?.accuracy_score !== null && detail?.accuracy_score !== undefined) {
      lines.push('');
      lines.push('QUALITY SCORE');
      lines.push('-'.repeat(60));
      lines.push(`Accuracy: ${Math.round(detail.accuracy_score)}%`);
      lines.push(`Compliance: ${Math.round(detail.compliance_score ?? 0)}%`);
      lines.push(`Empathy: ${Math.round(detail.empathy_score ?? 0)}%`);
      lines.push(`Resolution: ${Math.round(detail.resolution_score ?? 0)}%`);
      if (detail.qa_notes) {
        lines.push(detail.qa_notes);
      }
    }

    lines.push('');
    lines.push('TRANSCRIPT');
    lines.push('-'.repeat(60));

    if (entries.length === 0) {
      lines.push('No conversation recorded for this call.');
    }

    entries.forEach((entry, index) => {
      if (index > 0) {
        lines.push('');
      }
      const time = this.formatTime(entry.timestamp);
      if (entry.kind === 'message') {
        const conf = entry.confidence_score !== null ? ` (${Math.round(entry.confidence_score)}% confidence)` : '';
        lines.push(`${time}  ${entry.role.toUpperCase()}${conf}`);
        lines.push(this.indent(entry.content));
        if (entry.citations && entry.citations.length > 0) {
          for (const citation of entry.citations) {
            lines.push(
              this.indent(
                `Source: ${citation.filename}${citation.page ? ' p.' + citation.page : ''} (${Math.round(citation.confidence)}%)`,
              ),
            );
          }
        }
      } else {
        lines.push(`${time}  TOOL CALL — ${entry.tool_name}() (${Math.round(entry.execution_time_ms)}ms)`);
        lines.push(this.indent(`Input:  ${JSON.stringify(entry.input)}`));
        lines.push(this.indent(`Output: ${entry.output}`));
      }
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `transcript-${call.twilio_call_sid || call.id}.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  private formatTimestamp(value: string): string {
    const date = new Date(value);
    if (isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  }

  private formatTime(value: string): string {
    const date = new Date(value);
    if (isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  }

  private indent(text: string): string {
    return text
      .split('\n')
      .map((line) => `    ${line}`)
      .join('\n');
  }
}
