import { HttpClient, HttpEventType } from '@angular/common/http';
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
  readonly uploadProgress = signal<Record<string, number>>({});

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
    this.uploadProgress.update((current) => ({ ...current, [file.name]: 0 }));
    try {
      const formData = new FormData();
      formData.append('file', file);
      await new Promise<void>((resolve, reject) => {
        this.http
          .post(`${API_URL(agentId)}/upload`, formData, { reportProgress: true, observe: 'events' })
          .subscribe({
            next: (event) => {
              if (event.type === HttpEventType.UploadProgress && event.total) {
                const percent = Math.round((event.loaded / event.total) * 100);
                this.uploadProgress.update((current) => ({ ...current, [file.name]: percent }));
              } else if (event.type === HttpEventType.Response) {
                resolve();
              }
            },
            error: (err) => reject(err),
          });
      });
      await this.refresh(agentId);
    } catch {
      this.error.set(`Failed to upload ${file.name}.`);
    } finally {
      this.uploadProgress.update((current) => {
        const { [file.name]: _removed, ...rest } = current;
        return rest;
      });
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
