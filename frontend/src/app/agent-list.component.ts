import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Agent, AgentsService, DEPARTMENT_OPTIONS, VOICE_OPTIONS } from './agents.service';
import { ConfirmDialogComponent } from './shared/confirm-dialog.component';
import { VoiceCatalogEntry, voiceCatalogEntry } from './voice-catalog';
import { VoicePreviewService } from './voice-preview.service';

@Component({
  selector: 'app-agent-list',
  imports: [FormsModule, RouterLink, ConfirmDialogComponent],
  templateUrl: './agent-list.component.html',
  styleUrl: './agent-list.component.css',
})
export class AgentListComponent implements OnInit {
  readonly voiceOptions = VOICE_OPTIONS;
  readonly departmentOptions = DEPARTMENT_OPTIONS;
  readonly creating = signal(false);
  readonly searchTerm = signal('');

  readonly filteredAgents = computed(() => {
    const term = this.searchTerm().trim().toLowerCase();
    const agents = this.agents.agents();
    if (!term) return agents;
    return agents.filter(
      (a) => a.name.toLowerCase().includes(term) || a.persona.toLowerCase().includes(term),
    );
  });

  newName = '';
  newPersona = '';
  newVoice = VOICE_OPTIONS[0];
  newDepartment = DEPARTMENT_OPTIONS[0];

  readonly duplicating = signal<string | null>(null);
  readonly deleteTarget = signal<Agent | null>(null);
  readonly deleteError = signal<string | null>(null);
  readonly deleting = signal(false);

  constructor(
    protected readonly agents: AgentsService,
    protected readonly voicePreview: VoicePreviewService,
  ) {}

  ngOnInit(): void {
    this.agents.refresh();
  }

  voiceMeta(voiceId: string): VoiceCatalogEntry {
    return voiceCatalogEntry(voiceId);
  }

  async onCreate(): Promise<void> {
    if (!this.newName.trim()) return;
    this.creating.set(true);
    try {
      await this.agents.create(this.newName, this.newPersona, this.newVoice, this.newDepartment);
      this.newName = '';
      this.newPersona = '';
    } finally {
      this.creating.set(false);
    }
  }

  async onDuplicate(agent: Agent): Promise<void> {
    this.duplicating.set(agent.id);
    try {
      await this.agents.create(`${agent.name} (copy)`, agent.persona, agent.voice, agent.department);
    } finally {
      this.duplicating.set(null);
    }
  }

  requestDelete(agent: Agent): void {
    this.deleteError.set(null);
    this.deleteTarget.set(agent);
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteError.set(null);
  }

  async confirmDelete(): Promise<void> {
    const target = this.deleteTarget();
    if (!target) return;
    this.deleting.set(true);
    this.deleteError.set(null);
    try {
      await this.agents.remove(target.id);
      this.deleteTarget.set(null);
    } catch (err) {
      const detail =
        err instanceof HttpErrorResponse && typeof err.error?.detail === 'string'
          ? err.error.detail
          : 'Could not delete this agent.';
      this.deleteError.set(detail);
    } finally {
      this.deleting.set(false);
    }
  }
}
