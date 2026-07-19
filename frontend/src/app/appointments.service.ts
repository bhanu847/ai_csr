import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Appointment {
  id: string;
  agent_id: string;
  agent_name: string | null;
  caller_name: string;
  caller_phone: string;
  preferred_time: string;
  reason: string;
  created_at: string;
}

export interface AppointmentFilters {
  agent_id?: string;
  from_date?: string;
  to_date?: string;
}

const API_URL = 'http://localhost:8001/api/appointments';

@Injectable({ providedIn: 'root' })
export class AppointmentsService {
  readonly appointments = signal<Appointment[]>([]);
  readonly error = signal<string | null>(null);
  private activeFilters: AppointmentFilters = {};

  constructor(private readonly http: HttpClient) {}

  async refresh(filters?: AppointmentFilters): Promise<void> {
    if (filters) {
      this.activeFilters = filters;
    }
    let params = new HttpParams();
    for (const [key, value] of Object.entries(this.activeFilters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    try {
      const appointments = await firstValueFrom(
        this.http.get<Appointment[]>(API_URL, { params }),
      );
      this.appointments.set(appointments);
      this.error.set(null);
    } catch {
      this.error.set('Could not load appointments.');
    }
  }
}
