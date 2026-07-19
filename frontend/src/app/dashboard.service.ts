import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface CallVolumePoint {
  date: string;
  count: number;
}

export interface DashboardSummary {
  total_agents: number;
  total_calls: number;
  appointments_booked: number;
  calls_in_progress: number;
  call_volume: CallVolumePoint[];
}

const API_URL = 'http://localhost:8001/api/dashboard';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  readonly summary = signal<DashboardSummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(days = 14): Promise<void> {
    this.loading.set(true);
    try {
      const summary = await firstValueFrom(
        this.http.get<DashboardSummary>(API_URL + '/summary', { params: { days } }),
      );
      this.summary.set(summary);
      this.error.set(null);
    } catch {
      this.error.set('Could not load dashboard data. Is the backend running?');
    } finally {
      this.loading.set(false);
    }
  }
}
