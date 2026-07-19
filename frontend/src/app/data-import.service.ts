import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type ImportEntity = 'members' | 'claims' | 'drugs' | 'pharmacies';
export type FieldType = 'string' | 'number' | 'boolean' | 'date';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
}

export interface RowError {
  row: number;
  message: string;
}

export interface ImportResult {
  created: number;
  updated: number;
  errors: RowError[];
}

export const ENTITY_LABELS: Record<ImportEntity, string> = {
  members: 'Members',
  claims: 'Claims',
  drugs: 'Formulary drugs',
  pharmacies: 'Pharmacies',
};

export const ENTITY_FIELDS: Record<ImportEntity, FieldDef[]> = {
  members: [
    { key: 'member_id', label: 'Member ID', type: 'string', required: true },
    { key: 'first_name', label: 'First name', type: 'string', required: true },
    { key: 'last_name', label: 'Last name', type: 'string', required: true },
    { key: 'date_of_birth', label: 'Date of birth (YYYY-MM-DD)', type: 'date', required: true },
    { key: 'zip_code', label: 'ZIP code', type: 'string', required: true },
    { key: 'plan_name', label: 'Plan name', type: 'string', required: true },
    { key: 'group_number', label: 'Group number', type: 'string', required: true },
    { key: 'copay_primary_care', label: 'Primary care copay', type: 'number', required: true },
    { key: 'copay_specialist', label: 'Specialist copay', type: 'number', required: true },
    { key: 'copay_er', label: 'ER copay', type: 'number', required: true },
    { key: 'deductible', label: 'Deductible', type: 'number', required: true },
    { key: 'deductible_met', label: 'Deductible met so far', type: 'number', required: false },
  ],
  claims: [
    { key: 'claim_number', label: 'Claim number', type: 'string', required: true },
    { key: 'member_id', label: 'Member ID (must already be imported)', type: 'string', required: true },
    { key: 'service_date', label: 'Service date (YYYY-MM-DD)', type: 'date', required: true },
    { key: 'provider_name', label: 'Provider name', type: 'string', required: true },
    { key: 'description', label: 'Description', type: 'string', required: true },
    { key: 'amount', label: 'Amount', type: 'number', required: true },
    { key: 'status', label: 'Status (approved / rejected / pending)', type: 'string', required: true },
    { key: 'rejection_reason', label: 'Rejection reason', type: 'string', required: false },
  ],
  drugs: [
    { key: 'name', label: 'Drug name', type: 'string', required: true },
    { key: 'tier', label: 'Tier', type: 'number', required: true },
    { key: 'prior_auth_required', label: 'Prior auth required (true/false)', type: 'boolean', required: false },
    { key: 'copay', label: 'Copay', type: 'number', required: true },
    { key: 'notes', label: 'Notes', type: 'string', required: false },
  ],
  pharmacies: [
    { key: 'name', label: 'Pharmacy name', type: 'string', required: true },
    { key: 'address', label: 'Address', type: 'string', required: true },
    { key: 'zip_code', label: 'ZIP code', type: 'string', required: true },
    { key: 'phone', label: 'Phone', type: 'string', required: true },
    { key: 'in_network', label: 'In-network (true/false)', type: 'boolean', required: false },
  ],
};

const API_URL = 'http://localhost:8001/api/import';

@Injectable({ providedIn: 'root' })
export class DataImportService {
  constructor(private readonly http: HttpClient) {}

  async import(entity: ImportEntity, records: Record<string, unknown>[]): Promise<ImportResult> {
    try {
      return await firstValueFrom(this.http.post<ImportResult>(`${API_URL}/${entity}`, { records }));
    } catch (err) {
      const detail =
        err instanceof HttpErrorResponse && typeof err.error?.detail === 'string'
          ? err.error.detail
          : 'Import failed. Is the backend running?';
      throw new Error(detail);
    }
  }
}
