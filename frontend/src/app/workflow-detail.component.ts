import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { DEPARTMENT_OPTIONS } from './agents.service';
import { Workflow, WorkflowStepDraft, WorkflowsService } from './workflows.service';

@Component({
  selector: 'app-workflow-detail',
  imports: [FormsModule, RouterLink],
  templateUrl: './workflow-detail.component.html',
  styleUrl: './workflow-detail.component.css',
})
export class WorkflowDetailComponent implements OnInit {
  readonly departmentOptions = DEPARTMENT_OPTIONS;
  readonly workflow = signal<Workflow | null>(null);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);

  name = '';
  triggerDescription = '';
  department = '';
  isActive = true;
  steps: WorkflowStepDraft[] = [];

  private workflowId = '';

  constructor(
    private readonly route: ActivatedRoute,
    protected readonly workflows: WorkflowsService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.workflowId = this.route.snapshot.paramMap.get('id') ?? '';
    if (!this.workflowId) return;
    await this.workflows.refreshAvailableTools();
    try {
      const wf = await this.workflows.get(this.workflowId);
      this.workflow.set(wf);
      this.name = wf.name;
      this.triggerDescription = wf.trigger_description;
      this.department = wf.department ?? '';
      this.isActive = wf.is_active;
      this.steps = wf.steps
        .slice()
        .sort((a, b) => a.step_order - b.step_order)
        .map((s) => ({ tool_name: s.tool_name, condition: s.condition }));
    } catch {
      this.loadError.set('Workflow not found.');
    }
  }

  addStep(): void {
    const firstTool = this.workflows.availableTools()[0] ?? '';
    this.steps = [...this.steps, { tool_name: firstTool, condition: null }];
  }

  removeStep(index: number): void {
    this.steps = this.steps.filter((_, i) => i !== index);
  }

  moveStep(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.steps.length) return;
    const copy = [...this.steps];
    [copy[index], copy[target]] = [copy[target], copy[index]];
    this.steps = copy;
  }

  async onSave(): Promise<void> {
    this.saving.set(true);
    try {
      const updated = await this.workflows.update(this.workflowId, {
        name: this.name,
        trigger_description: this.triggerDescription,
        department: this.department || null,
        is_active: this.isActive,
        steps: this.steps,
      });
      this.workflow.set(updated);
    } finally {
      this.saving.set(false);
    }
  }
}
