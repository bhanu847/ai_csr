import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Agent {
  id: string;
  name: string;
  persona: string;
  voice: string;
  is_default: boolean;
}

const API_URL = 'http://localhost:8001/api/agents';

export const VOICE_OPTIONS = [
  'en-IN-NeerjaNeural',
  'hi-IN-SwaraNeural',
  'en-US-JennyNeural',
  'en-US-GuyNeural',
];

@Injectable({ providedIn: 'root' })
export class AgentsService {
  readonly agents = signal<Agent[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const agents = await firstValueFrom(this.http.get<Agent[]>(API_URL));
      this.agents.set(agents);
      this.error.set(null);
    } catch {
      this.error.set('Could not load agents. Is the backend running?');
    }
  }

  async create(name: string, persona: string, voice: string): Promise<Agent> {
    const agent = await firstValueFrom(
      this.http.post<Agent>(API_URL, { name, persona, voice }),
    );
    await this.refresh();
    return agent;
  }

  async get(agentId: string): Promise<Agent> {
    return firstValueFrom(this.http.get<Agent>(`${API_URL}/${agentId}`));
  }

  async update(
    agentId: string,
    changes: Partial<Pick<Agent, 'name' | 'persona' | 'voice' | 'is_default'>>,
  ): Promise<Agent> {
    const agent = await firstValueFrom(this.http.patch<Agent>(`${API_URL}/${agentId}`, changes));
    await this.refresh();
    return agent;
  }
}
