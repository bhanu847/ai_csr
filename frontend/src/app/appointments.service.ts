import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Appointment {
  id: string;
  agent_id: string;
  caller_name: string;
  caller_phone: string;
  preferred_time: string;
  reason: string;
  created_at: string;
}

const API_URL = 'http://localhost:8001/api/appointments';

@Injectable({ providedIn: 'root' })
export class AppointmentsService {
  readonly appointments = signal<Appointment[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const appointments = await firstValueFrom(this.http.get<Appointment[]>(API_URL));
      this.appointments.set(appointments);
      this.error.set(null);
    } catch {
      this.error.set('Could not load appointments.');
    }
  }
}
