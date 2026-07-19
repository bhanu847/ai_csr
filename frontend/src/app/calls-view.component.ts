import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';

import { AppointmentsService } from './appointments.service';
import { CallsService } from './calls.service';

const POLL_INTERVAL_MS = 5000;

@Component({
  selector: 'app-calls-view',
  imports: [DatePipe],
  templateUrl: './calls-view.component.html',
  styleUrl: './calls-view.component.css',
})
export class CallsViewComponent implements OnInit, OnDestroy {
  private pollHandle?: ReturnType<typeof setInterval>;

  constructor(
    protected readonly calls: CallsService,
    protected readonly appointments: AppointmentsService,
  ) {}

  ngOnInit(): void {
    this.refresh();
    this.pollHandle = setInterval(() => this.refresh(), POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
    }
  }

  private refresh(): void {
    this.calls.refresh();
    this.appointments.refresh();
  }
}
