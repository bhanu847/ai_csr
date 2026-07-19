import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AgentsService, VOICE_OPTIONS } from './agents.service';

@Component({
  selector: 'app-agent-list',
  imports: [FormsModule, RouterLink],
  templateUrl: './agent-list.component.html',
  styleUrl: './agent-list.component.css',
})
export class AgentListComponent implements OnInit {
  readonly voiceOptions = VOICE_OPTIONS;
  readonly creating = signal(false);

  newName = '';
  newPersona = '';
  newVoice = VOICE_OPTIONS[0];

  constructor(protected readonly agents: AgentsService) {}

  ngOnInit(): void {
    this.agents.refresh();
  }

  async onCreate(): Promise<void> {
    if (!this.newName.trim()) return;
    this.creating.set(true);
    try {
      await this.agents.create(this.newName, this.newPersona, this.newVoice);
      this.newName = '';
      this.newPersona = '';
    } finally {
      this.creating.set(false);
    }
  }
}
