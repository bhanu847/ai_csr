import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type FeedbackOutcome =
  | 'confirmed'
  | 'reinforced'
  | 'corrected'
  | 'regenerated'
  | 'not_in_documents'
  | 'recorded';

export interface LearnedAnswer {
  id: string;
  agent_id: string;
  question: string;
  answer: string | null;
  origin: 'correction' | 'regenerated' | 'confirmed' | 'unanswered';
  positive: number;
  negative: number;
  uses: number;
  active: boolean;
  updated_at: string;
}

export interface FeedbackResult {
  feedback_id: string;
  outcome: FeedbackOutcome;
  message: string;
  learned_answer: LearnedAnswer | null;
}

const API_URL = 'http://localhost:8001/api/feedback';

@Injectable({ providedIn: 'root' })
export class FeedbackService {
  readonly learned = signal<LearnedAnswer[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  /** Thumbs up/down on an assistant reply. A thumbs-down without a correction
   * makes the backend re-answer from the agent's documents, which can take a
   * while on CPU-only LLM hardware. */
  async submit(messageId: string, helpful: boolean, correction?: string): Promise<FeedbackResult> {
    try {
      return await firstValueFrom(
        this.http.post<FeedbackResult>(API_URL, {
          message_id: messageId,
          helpful,
          correction: correction?.trim() || null,
        }),
      );
    } catch (err) {
      const detail =
        err instanceof HttpErrorResponse && typeof err.error?.detail === 'string'
          ? err.error.detail
          : 'Could not save feedback. Is the backend running?';
      throw new Error(detail);
    }
  }

  async refreshLearned(): Promise<void> {
    try {
      this.learned.set(await firstValueFrom(this.http.get<LearnedAnswer[]>(`${API_URL}/learned`)));
      this.error.set(null);
    } catch {
      this.error.set('Could not load learned answers.');
    }
  }

  async setActive(id: string, active: boolean): Promise<void> {
    const updated = await firstValueFrom(this.http.patch<LearnedAnswer>(`${API_URL}/learned/${id}`, { active }));
    this.learned.set(this.learned().map((a) => (a.id === id ? updated : a)));
  }
}
