import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Call } from './calls.service';

export interface LiveCall extends Call {
  customer_name: string | null;
  department: string | null;
  ai_paused: boolean;
  latest_message_role: 'customer' | 'assistant' | 'system' | 'tool' | null;
  latest_message_preview: string | null;
  latest_confidence: number | null;
}

const API_URL = 'http://localhost:8001/api/supervisor';

@Injectable({ providedIn: 'root' })
export class SupervisorService {
  readonly liveCalls = signal<LiveCall[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const liveCalls = await firstValueFrom(this.http.get<LiveCall[]>(`${API_URL}/live-calls`));
      this.liveCalls.set(liveCalls);
      this.error.set(null);
    } catch {
      this.error.set('Could not load live calls. Is the backend running?');
    }
  }

  async pause(callId: string): Promise<void> {
    await firstValueFrom(this.http.post(`${API_URL}/calls/${callId}/pause`, {}));
    await this.refresh();
  }

  async resume(callId: string): Promise<void> {
    await firstValueFrom(this.http.post(`${API_URL}/calls/${callId}/resume`, {}));
    await this.refresh();
  }

  async sendSuggestion(callId: string, suggestion: string): Promise<void> {
    await firstValueFrom(this.http.post(`${API_URL}/calls/${callId}/suggest`, { suggestion }));
    await this.refresh();
  }
}
