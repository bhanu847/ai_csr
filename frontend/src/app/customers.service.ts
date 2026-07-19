import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Customer {
  id: string;
  phone_number: string;
  name: string | null;
  language: string | null;
  last_interaction: string | null;
  created_at: string;
}

export interface PreviousCall {
  id: string;
  started_at: string;
  intent: string | null;
  sentiment: string | null;
  resolution_status: string | null;
  summary: string | null;
}

export interface CustomerDetail extends Customer {
  call_count: number;
  latest_sentiment: string | null;
  previous_calls: PreviousCall[];
}

const API_URL = 'http://localhost:8001/api/customers';

@Injectable({ providedIn: 'root' })
export class CustomersService {
  readonly customers = signal<Customer[]>([]);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(): Promise<void> {
    try {
      const customers = await firstValueFrom(this.http.get<Customer[]>(API_URL));
      this.customers.set(customers);
      this.error.set(null);
    } catch {
      this.error.set('Could not load customers. Is the backend running?');
    }
  }

  async getDetail(customerId: string): Promise<CustomerDetail> {
    return firstValueFrom(this.http.get<CustomerDetail>(`${API_URL}/${customerId}`));
  }
}
