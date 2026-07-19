import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import Papa from 'papaparse';

import {
  DataImportService,
  ENTITY_FIELDS,
  ENTITY_LABELS,
  FieldDef,
  ImportEntity,
  ImportResult,
} from './data-import.service';

const ENTITY_ORDER: ImportEntity[] = ['members', 'claims', 'drugs', 'pharmacies'];

@Component({
  selector: 'app-data-import',
  imports: [FormsModule],
  templateUrl: './data-import.component.html',
  styleUrl: './data-import.component.css',
})
export class DataImportComponent {
  constructor(private readonly dataImport: DataImportService) {}

  readonly entityOrder = ENTITY_ORDER;
  readonly entityLabels = ENTITY_LABELS;

  selectedEntity = signal<ImportEntity>('members');
  readonly fields = computed<FieldDef[]>(() => ENTITY_FIELDS[this.selectedEntity()]);

  fileName = signal<string | null>(null);
  csvHeaders = signal<string[]>([]);
  csvRows = signal<Record<string, string>[]>([]);
  mapping: Record<string, string> = {};

  parseError = signal<string | null>(null);
  mappingError = signal<string | null>(null);
  importing = signal(false);
  result = signal<ImportResult | null>(null);

  readonly previewRows = computed(() => this.csvRows().slice(0, 5));

  onEntityChange(): void {
    this.resetFile();
  }

  resetFile(): void {
    this.fileName.set(null);
    this.csvHeaders.set([]);
    this.csvRows.set([]);
    this.mapping = {};
    this.result.set(null);
    this.parseError.set(null);
    this.mappingError.set(null);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    this.resetFile();
    this.fileName.set(file.name);

    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          this.parseError.set('No columns detected — is this a valid CSV with a header row?');
          return;
        }
        this.csvHeaders.set(headers);
        this.csvRows.set(results.data);
        this.autoMapColumns(headers);
      },
      error: (err: Error) => {
        this.parseError.set(`Could not parse CSV: ${err.message}`);
      },
    });
  }

  private autoMapColumns(headers: string[]): void {
    const normalize = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    for (const field of this.fields()) {
      const match = headers.find(
        (h) => normalize(h) === normalize(field.key) || normalize(h) === normalize(field.label),
      );
      this.mapping[field.key] = match ?? '';
    }
  }

  mappedPreviewValue(field: FieldDef, row: Record<string, string>): string {
    const header = this.mapping[field.key];
    if (!header) return '—';
    const value = row[header];
    return value?.trim() ? value : '—';
  }

  async onImport(): Promise<void> {
    this.mappingError.set(null);
    this.result.set(null);

    const missing = this.fields().filter((f) => f.required && !this.mapping[f.key]);
    if (missing.length > 0) {
      this.mappingError.set(`Map a column for: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }

    const records = this.csvRows().map((rawRow) => {
      const record: Record<string, unknown> = {};
      for (const field of this.fields()) {
        const header = this.mapping[field.key];
        let value: string | null = header ? rawRow[header] : null;
        if (typeof value === 'string') {
          value = value.trim();
          if (value === '') value = null;
        }
        record[field.key] = value;
      }
      return record;
    });

    this.importing.set(true);
    try {
      this.result.set(await this.dataImport.import(this.selectedEntity(), records));
    } catch (err) {
      this.mappingError.set(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      this.importing.set(false);
    }
  }
}
