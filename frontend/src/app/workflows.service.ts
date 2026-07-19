import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface WorkflowStep {
  id: string;
  step_order: number;
  tool_name: string;
  condition: string | null;
}

export interface WorkflowStepDraft {
  tool_name: string;
  condition: string | null;
}

export interface Workflow {
  id: string;
  name: string;
  trigger_description: string;
  department: string | null;
  is_active: boolean;
  created_at: string;
  steps: WorkflowStep[];
}

const API_URL = 'http://localhost:8001/api/workflows';

@Injectable({ providedIn: 'root' })
export class WorkflowsService {
  readonly workflows = signal<Workflow[]>([]);
  readonly error = signal<string | null>(null);
  readonly availableTools = signal<string[]>([]);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const workflows = await firstValueFrom(this.http.get<Workflow[]>(API_URL));
      this.workflows.set(workflows);
      this.error.set(null);
    } catch {
      this.error.set('Could not load workflows. Is the backend running?');
    }
  }

  async refreshAvailableTools(): Promise<void> {
    try {
      this.availableTools.set(await firstValueFrom(this.http.get<string[]>(`${API_URL}/available-tools`)));
    } catch {
      // Non-critical — the step editor falls back to a free-text tool name if this fails.
    }
  }

  async get(id: string): Promise<Workflow> {
    return firstValueFrom(this.http.get<Workflow>(`${API_URL}/${id}`));
  }

  async create(
    name: string,
    triggerDescription: string,
    department: string | null,
    steps: WorkflowStepDraft[] = [],
  ): Promise<Workflow> {
    const workflow = await firstValueFrom(
      this.http.post<Workflow>(API_URL, {
        name,
        trigger_description: triggerDescription,
        department,
        steps,
      }),
    );
    await this.refresh();
    return workflow;
  }

  async update(
    id: string,
    changes: Partial<{
      name: string;
      trigger_description: string;
      department: string | null;
      is_active: boolean;
      steps: WorkflowStepDraft[];
    }>,
  ): Promise<Workflow> {
    const workflow = await firstValueFrom(this.http.patch<Workflow>(`${API_URL}/${id}`, changes));
    await this.refresh();
    return workflow;
  }

  async remove(id: string): Promise<void> {
    await firstValueFrom(this.http.delete(`${API_URL}/${id}`));
    await this.refresh();
  }
}
