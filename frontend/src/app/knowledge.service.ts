import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface KnowledgeDocument {
  id: string;
  filename: string;
  chunk_count: number;
}

const API_URL = (agentId: string) => `http://localhost:8001/api/agents/${agentId}/knowledge`;

@Injectable({ providedIn: 'root' })
export class KnowledgeService {
  readonly documents = signal<KnowledgeDocument[]>([]);
  readonly uploading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  async refresh(agentId: string): Promise<void> {
    try {
      const docs = await firstValueFrom(this.http.get<KnowledgeDocument[]>(API_URL(agentId)));
      this.documents.set(docs);
      this.error.set(null);
    } catch {
      this.error.set('Could not load knowledge base.');
    }
  }

  async upload(agentId: string, file: File): Promise<void> {
    this.uploading.set(true);
    this.error.set(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await firstValueFrom(this.http.post(`${API_URL(agentId)}/upload`, formData));
      await this.refresh(agentId);
    } catch {
      this.error.set(`Failed to upload ${file.name}.`);
    } finally {
      this.uploading.set(false);
    }
  }

  async delete(agentId: string, documentId: string): Promise<void> {
    try {
      await firstValueFrom(this.http.delete(`${API_URL(agentId)}/${documentId}`));
      await this.refresh(agentId);
    } catch {
      this.error.set('Failed to delete document.');
    }
  }
}
