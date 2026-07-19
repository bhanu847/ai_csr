import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type InsightCategory = 'missing_knowledge' | 'prompt_improvement' | 'workflow_improvement';
export type InsightStatus = 'new' | 'acknowledged' | 'dismissed';

export interface TrainingInsight {
  id: string;
  category: InsightCategory;
  title: string;
  description: string;
  supporting_call_count: number;
  status: InsightStatus;
  created_at: string;
}

interface AnalyzeResponse {
  insights: TrainingInsight[];
  message: string;
}

const API_URL = 'http://localhost:8001/api/training';

@Injectable({ providedIn: 'root' })
export class TrainingService {
  readonly insights = signal<TrainingInsight[]>([]);
  readonly loading = signal(false);
  readonly analyzing = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastAnalysisMessage = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    this.loading.set(true);
    try {
      const insights = await firstValueFrom(this.http.get<TrainingInsight[]>(`${API_URL}/insights`));
      this.insights.set(insights);
      this.error.set(null);
    } catch {
      this.error.set('Could not load training insights. Is the backend running?');
    } finally {
      this.loading.set(false);
    }
  }

  async analyze(): Promise<void> {
    this.analyzing.set(true);
    this.lastAnalysisMessage.set(null);
    try {
      const result = await firstValueFrom(this.http.post<AnalyzeResponse>(`${API_URL}/analyze`, {}));
      this.lastAnalysisMessage.set(result.message);
      this.error.set(null);
      await this.refresh();
    } catch (err) {
      const detail =
        err instanceof HttpErrorResponse && typeof err.error?.detail === 'string'
          ? err.error.detail
          : 'Analysis failed. Is the backend running?';
      this.error.set(detail);
    } finally {
      this.analyzing.set(false);
    }
  }

  async updateStatus(id: string, status: InsightStatus): Promise<void> {
    const updated = await firstValueFrom(
      this.http.patch<TrainingInsight>(`${API_URL}/insights/${id}`, { status }),
    );
    this.insights.set(this.insights().map((i) => (i.id === id ? updated : i)));
  }
}
