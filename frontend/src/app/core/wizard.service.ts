import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { Question } from '../models';

export type Step = 'scan' | 'questions' | 'report';

@Injectable({ providedIn: 'root' })
export class WizardService {
  private readonly api = inject(ApiService);

  readonly step = signal<Step>('scan');
  readonly sessionId = signal('');
  readonly questions = signal<Question[]>([]);
  readonly answers = signal<Record<string, string>>({});
  readonly reportMarkdown = signal('');
  readonly isExample = signal(false);

  startQuestions(sessionId: string, questions: Question[]): void {
    this.sessionId.set(sessionId);
    this.questions.set(questions);
    this.answers.set({});
    this.step.set('questions');
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
    this.step.set('report');
  }

  async showExample(): Promise<void> {
    const text = await this.api.example();
    this.reportMarkdown.set(text);
    this.isExample.set(true);
    this.step.set('report');
  }

  backFromReport(): void {
    if (this.isExample()) {
      this.isExample.set(false);
      this.step.set('scan');
    } else {
      this.step.set('questions');
    }
  }

  goTo(step: Step): void {
    this.step.set(step);
  }
}
