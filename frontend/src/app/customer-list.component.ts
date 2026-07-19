import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { CustomerDetailDrawerComponent } from './customer-detail-drawer.component';
import { Customer, CustomersService } from './customers.service';

@Component({
  selector: 'app-customer-list',
  imports: [DatePipe, FormsModule, CustomerDetailDrawerComponent],
  templateUrl: './customer-list.component.html',
  styleUrl: './customer-list.component.css',
})
export class CustomerListComponent implements OnInit {
  readonly selectedCustomer = signal<Customer | null>(null);
  searchTerm = signal('');

  readonly filteredCustomers = computed(() => {
    const term = this.searchTerm().trim().toLowerCase();
    const customers = this.customers.customers();
    if (!term) return customers;
    return customers.filter(
      (c) => (c.name ?? '').toLowerCase().includes(term) || c.phone_number.includes(term),
    );
  });

  constructor(protected readonly customers: CustomersService) {}

  ngOnInit(): void {
    this.customers.refresh();
  }
}
