import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { Agent, AgentsService, VOICE_OPTIONS } from './agents.service';
import { KnowledgeService } from './knowledge.service';

@Component({
  selector: 'app-agent-detail',
  imports: [FormsModule, RouterLink],
  templateUrl: './agent-detail.component.html',
  styleUrl: './agent-detail.component.css',
})
export class AgentDetailComponent implements OnInit {
  readonly voiceOptions = VOICE_OPTIONS;
  readonly agent = signal<Agent | null>(null);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);

  agentId = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly agentsService: AgentsService,
    protected readonly knowledge: KnowledgeService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.agentId = this.route.snapshot.paramMap.get('id') ?? '';
    if (!this.agentId) return;
    try {
      const agent = await this.agentsService.get(this.agentId);
      this.agent.set(agent);
    } catch {
      this.loadError.set('Agent not found.');
      return;
    }
    await this.knowledge.refresh(this.agentId);
  }

  async onSave(): Promise<void> {
    const agent = this.agent();
    if (!agent) return;
    this.saving.set(true);
    try {
      const updated = await this.agentsService.update(this.agentId, {
        name: agent.name,
        persona: agent.persona,
        voice: agent.voice,
      });
      this.agent.set(updated);
    } finally {
      this.saving.set(false);
    }
  }

  async onMakeDefault(): Promise<void> {
    const updated = await this.agentsService.update(this.agentId, { is_default: true });
    this.agent.set(updated);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.knowledge.upload(this.agentId, file);
    }
    input.value = '';
  }

  onDeleteDocument(documentId: string): void {
    this.knowledge.delete(this.agentId, documentId);
  }
}
