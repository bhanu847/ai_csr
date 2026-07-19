import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Call {
  id: string;
  agent_id: string | null;
  agent_name: string | null;
  twilio_call_sid: string;
  from_number: string;
  to_number: string;
  status: 'in_progress' | 'completed' | 'failed';
  intent: string | null;
  sentiment: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface CallDetail extends Call {
  confidence_score: number | null;
  summary: string | null;
  resolution_status: 'resolved' | 'escalated' | 'abandoned' | null;
}

export interface Citation {
  filename: string;
  page: number | null;
  confidence: number;
}

export interface TranscriptMessage {
  kind: 'message';
  timestamp: string;
  role: 'customer' | 'assistant' | 'system' | 'tool';
  content: string;
  message_type: string;
  confidence_score: number | null;
  citations: Citation[] | null;
}

export interface TranscriptToolCall {
  kind: 'tool_call';
  timestamp: string;
  tool_name: string;
  input: Record<string, unknown>;
  output: string;
  execution_time_ms: number;
}

export type TranscriptEntry = TranscriptMessage | TranscriptToolCall;

export interface CallFilters {
  status?: string;
  agent_id?: string;
  from_date?: string;
  to_date?: string;
}

const API_URL = 'http://localhost:8001/api/calls';

@Injectable({ providedIn: 'root' })
export class CallsService {
  readonly calls = signal<Call[]>([]);
  readonly error = signal<string | null>(null);
  private activeFilters: CallFilters = {};

  constructor(private readonly http: HttpClient) {}

  async refresh(filters?: CallFilters): Promise<void> {
    if (filters) {
      this.activeFilters = filters;
    }
    let params = new HttpParams();
    for (const [key, value] of Object.entries(this.activeFilters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    try {
      const calls = await firstValueFrom(this.http.get<Call[]>(API_URL, { params }));
      this.calls.set(calls);
      this.error.set(null);
    } catch {
      this.error.set('Could not load calls. Is the backend running?');
    }
  }

  async getDetail(callId: string): Promise<CallDetail> {
    return firstValueFrom(this.http.get<CallDetail>(`${API_URL}/${callId}`));
  }

  async getTranscript(callId: string): Promise<TranscriptEntry[]> {
    return firstValueFrom(this.http.get<TranscriptEntry[]>(`${API_URL}/${callId}/transcript`));
  }
}
