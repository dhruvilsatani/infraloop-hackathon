import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AnswerResponse, ScanResponse, UploadFile } from '../models';

export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof HttpErrorResponse && typeof err.error?.detail === 'string') {
    return err.error.detail;
  }
  return fallback;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  startUpload(): Promise<{ upload_id: string }> {
    return firstValueFrom(this.http.post<{ upload_id: string }>('/upload/start', {}));
  }

  uploadFiles(uploadId: string, files: UploadFile[]): Promise<unknown> {
    return firstValueFrom(this.http.post(`/upload/${uploadId}/files`, { files }));
  }

  scan(repoPathOrUrl: string, uploadId: string, notes: string): Promise<ScanResponse> {
    return firstValueFrom(
      this.http.post<ScanResponse>('/scan', { repo_path_or_url: repoPathOrUrl, upload_id: uploadId, notes }),
    );
  }

  answer(sessionId: string, answers: Record<string, string>, mode: string): Promise<AnswerResponse> {
    return firstValueFrom(this.http.post<AnswerResponse>('/answer', { session_id: sessionId, answers, mode }));
  }

  example(): Promise<string> {
    return firstValueFrom(this.http.get('/assets/example-report.md', { responseType: 'text' }));
  }
}
