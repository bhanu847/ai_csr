import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface CallVolumePoint {
  date: string;
  count: number;
}

export interface RecentConversation {
  id: string;
  from_number: string;
  agent_name: string | null;
  intent: string | null;
  sentiment: string | null;
  resolution_status: string | null;
  started_at: string;
}

export interface DashboardSummary {
  total_agents: number;
  agents_on_active_calls: number;
  total_calls: number;
  appointments_booked: number;
  calls_in_progress: number;
  resolution_rate: number;
  escalation_rate: number;
  avg_handle_time_seconds: number | null;
  cost_saved_estimate: number;
  cost_saved_assumption_per_call: number;
  call_volume: CallVolumePoint[];
  recent_conversations: RecentConversation[];
}

export interface IntentCount {
  intent: string;
  count: number;
}

export interface SentimentCount {
  sentiment: string;
  count: number;
}

export interface ResolutionTrendPoint {
  date: string;
  resolved: number;
  escalated: number;
  abandoned: number;
}

export interface AnalyticsSummary {
  top_intents: IntentCount[];
  sentiment_mix: SentimentCount[];
  resolution_trend: ResolutionTrendPoint[];
}

const API_URL = 'http://localhost:8001/api/dashboard';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  readonly summary = signal<DashboardSummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly analytics = signal<AnalyticsSummary | null>(null);
  readonly analyticsLoading = signal(false);
  readonly analyticsError = signal<string | null>(null);

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

  async refreshAnalytics(days = 14): Promise<void> {
    this.analyticsLoading.set(true);
    try {
      const analytics = await firstValueFrom(
        this.http.get<AnalyticsSummary>(API_URL + '/analytics', { params: { days } }),
      );
      this.analytics.set(analytics);
      this.analyticsError.set(null);
    } catch {
      this.analyticsError.set('Could not load analytics data. Is the backend running?');
    } finally {
      this.analyticsLoading.set(false);
    }
  }
}
