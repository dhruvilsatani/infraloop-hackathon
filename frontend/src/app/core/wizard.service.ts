import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from './api.service';
import { Question } from '../models';

// Holds the data that flows through the pages. The current page is the router URL, not a state here.
@Injectable({ providedIn: 'root' })
export class WizardService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly sessionId = signal('');
  readonly questions = signal<Question[]>([]);
  readonly answers = signal<Record<string, string>>({});
  readonly reportMarkdown = signal('');
  readonly isExample = signal(false);

  startQuestions(sessionId: string, questions: Question[]): void {
    this.sessionId.set(sessionId);
    this.questions.set(questions);
    this.answers.set({});
  }

  setQuestions(questions: Question[]): void {
    this.questions.set(questions);
  }

  setAnswer(question: string, value: string): void {
    this.answers.update((a) => ({ ...a, [question]: value }));
  }

  showReport(markdown: string): void {
    this.reportMarkdown.set(markdown);
    this.isExample.set(false);
  }

  async openExample(): Promise<void> {
    const text = await this.api.example();
    this.reportMarkdown.set(text);
    this.isExample.set(true);
    await this.router.navigate(['/report']);
  }

  startNewScan(): void {
    this.sessionId.set('');
    this.questions.set([]);
    this.answers.set({});
    this.reportMarkdown.set('');
    this.isExample.set(false);
    this.router.navigate(['/scan']);
  }
}
