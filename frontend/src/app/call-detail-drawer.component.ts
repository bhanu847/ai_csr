import { DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { Call } from './calls.service';
import { formatDuration } from './format-duration';

@Component({
  selector: 'app-call-detail-drawer',
  imports: [DatePipe],
  templateUrl: './call-detail-drawer.component.html',
  styleUrl: './call-detail-drawer.component.css',
})
export class CallDetailDrawerComponent {
  @Input() call: Call | null = null;
  @Output() readonly closed = new EventEmitter<void>();

  duration(call: Call): string {
    return formatDuration(call.started_at, call.ended_at);
  }
}
