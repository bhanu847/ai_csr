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
  started_at: string;
  ended_at: string | null;
}

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
}
