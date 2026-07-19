import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { DEPARTMENT_OPTIONS } from './agents.service';
import { ConfirmDialogComponent } from './shared/confirm-dialog.component';
import { Workflow, WorkflowsService } from './workflows.service';

@Component({
  selector: 'app-workflow-list',
  imports: [FormsModule, RouterLink, ConfirmDialogComponent],
  templateUrl: './workflow-list.component.html',
  styleUrl: './workflow-list.component.css',
})
export class WorkflowListComponent implements OnInit {
  readonly departmentOptions = DEPARTMENT_OPTIONS;
  readonly creating = signal(false);

  newName = '';
  newTrigger = '';
  newDepartment = '';

  readonly deleteTarget = signal<Workflow | null>(null);
  readonly deleting = signal(false);

  constructor(protected readonly workflows: WorkflowsService) {}

  ngOnInit(): void {
    this.workflows.refresh();
  }

  async onCreate(): Promise<void> {
    if (!this.newName.trim() || !this.newTrigger.trim()) return;
    this.creating.set(true);
    try {
      await this.workflows.create(this.newName, this.newTrigger, this.newDepartment || null);
      this.newName = '';
      this.newTrigger = '';
      this.newDepartment = '';
    } finally {
      this.creating.set(false);
    }
  }

  requestDelete(workflow: Workflow): void {
    this.deleteTarget.set(workflow);
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
  }

  async confirmDelete(): Promise<void> {
    const target = this.deleteTarget();
    if (!target) return;
    this.deleting.set(true);
    try {
      await this.workflows.remove(target.id);
      this.deleteTarget.set(null);
    } finally {
      this.deleting.set(false);
    }
  }

  async onToggleActive(workflow: Workflow): Promise<void> {
    await this.workflows.update(workflow.id, { is_active: !workflow.is_active });
  }
}
