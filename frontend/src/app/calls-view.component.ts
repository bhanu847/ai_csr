import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentsService } from './agents.service';
import { AppointmentsService } from './appointments.service';
import { CallDetailDrawerComponent } from './call-detail-drawer.component';
import { Call, CallsService } from './calls.service';
import { formatDuration } from './format-duration';

const POLL_INTERVAL_MS = 5000;

type Tab = 'calls' | 'appointments';

@Component({
  selector: 'app-calls-view',
  imports: [DatePipe, FormsModule, CallDetailDrawerComponent],
  templateUrl: './calls-view.component.html',
  styleUrl: './calls-view.component.css',
})
export class CallsViewComponent implements OnInit, OnDestroy {
  private pollHandle?: ReturnType<typeof setInterval>;

  readonly activeTab = signal<Tab>('calls');
  readonly selectedCall = signal<Call | null>(null);

  statusFilter = '';
  callAgentFilter = '';
  callFromDate = '';
  callToDate = '';

  apptAgentFilter = '';
  apptFromDate = '';
  apptToDate = '';

  constructor(
    protected readonly calls: CallsService,
    protected readonly appointments: AppointmentsService,
    protected readonly agents: AgentsService,
  ) {}

  ngOnInit(): void {
    this.agents.refresh();
    this.applyCallFilters();
    this.applyAppointmentFilters();
    this.pollHandle = setInterval(() => {
      this.calls.refresh();
      this.appointments.refresh();
    }, POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
    }
  }

  applyCallFilters(): void {
    this.calls.refresh({
      status: this.statusFilter || undefined,
      agent_id: this.callAgentFilter || undefined,
      from_date: this.callFromDate || undefined,
      to_date: this.callToDate || undefined,
    });
  }

  applyAppointmentFilters(): void {
    this.appointments.refresh({
      agent_id: this.apptAgentFilter || undefined,
      from_date: this.apptFromDate || undefined,
      to_date: this.apptToDate || undefined,
    });
  }

  duration(call: Call): string {
    return formatDuration(call.started_at, call.ended_at);
  }
}
