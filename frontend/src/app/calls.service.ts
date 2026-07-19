import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Call {
  id: string;
  agent_id: string | null;
  twilio_call_sid: string;
  from_number: string;
  to_number: string;
  status: 'in_progress' | 'completed' | 'failed';
  started_at: string;
  ended_at: string | null;
}

const API_URL = 'http://localhost:8001/api/calls';

@Injectable({ providedIn: 'root' })
export class CallsService {
  readonly calls = signal<Call[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const calls = await firstValueFrom(this.http.get<Call[]>(API_URL));
      this.calls.set(calls);
      this.error.set(null);
    } catch {
      this.error.set('Could not load calls. Is the backend running?');
    }
  }
}
