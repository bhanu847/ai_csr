import { DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges, signal } from '@angular/core';

import { Customer, CustomerDetail, CustomersService } from './customers.service';

@Component({
  selector: 'app-customer-detail-drawer',
  imports: [DatePipe],
  templateUrl: './customer-detail-drawer.component.html',
  styleUrl: './customer-detail-drawer.component.css',
})
export class CustomerDetailDrawerComponent implements OnChanges {
  @Input() customer: Customer | null = null;
  @Output() readonly closed = new EventEmitter<void>();

  readonly detail = signal<CustomerDetail | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private readonly customers: CustomersService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['customer']) {
      return;
    }
    this.detail.set(null);
    this.error.set(null);
    if (this.customer) {
      this.load(this.customer.id);
    }
  }

  private async load(customerId: string): Promise<void> {
    this.loading.set(true);
    try {
      this.detail.set(await this.customers.getDetail(customerId));
    } catch {
      this.error.set('Could not load customer detail.');
    } finally {
      this.loading.set(false);
    }
  }
}
