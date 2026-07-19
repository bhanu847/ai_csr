import { KeyValuePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { Agent, AgentsService, DEPARTMENT_OPTIONS, VOICE_OPTIONS } from './agents.service';
import { KnowledgeService } from './knowledge.service';
import { VoiceCatalogEntry, voiceCatalogEntry } from './voice-catalog';
import { VoicePreviewService } from './voice-preview.service';

export type FileKind = 'pdf' | 'docx' | 'generic';

@Component({
  selector: 'app-agent-detail',
  imports: [FormsModule, RouterLink, KeyValuePipe],
  templateUrl: './agent-detail.component.html',
  styleUrl: './agent-detail.component.css',
})
export class AgentDetailComponent implements OnInit {
  readonly voiceOptions = VOICE_OPTIONS;
  readonly departmentOptions = DEPARTMENT_OPTIONS;
  readonly agent = signal<Agent | null>(null);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly dragActive = signal(false);

  agentId = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly agentsService: AgentsService,
    protected readonly knowledge: KnowledgeService,
    protected readonly voicePreview: VoicePreviewService,
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

  voiceMeta(voiceId: string): VoiceCatalogEntry {
    return voiceCatalogEntry(voiceId);
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
        department: agent.department,
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
    if (input.files) {
      this.uploadFiles(input.files);
    }
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(true);
  }

  onDragLeave(): void {
    this.dragActive.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(false);
    if (event.dataTransfer?.files) {
      this.uploadFiles(event.dataTransfer.files);
    }
  }

  onDeleteDocument(documentId: string): void {
    this.knowledge.delete(this.agentId, documentId);
  }

  fileIcon(filename: string): FileKind {
    const lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) return 'pdf';
    if (lower.endsWith('.docx')) return 'docx';
    return 'generic';
  }

  private uploadFiles(fileList: FileList): void {
    const allowed = Array.from(fileList).filter((file) => /\.(pdf|docx)$/i.test(file.name));
    for (const file of allowed) {
      this.knowledge.upload(this.agentId, file);
    }
    if (allowed.length === 0 && fileList.length > 0) {
      this.knowledge.error.set('Only PDF and DOCX files are supported.');
    }
  }
}
