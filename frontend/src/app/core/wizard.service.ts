import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from './api.service';
import { Budget, GapItem, PreviewResponse, Question, Target } from '../models';

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

  // From POST /answer, next to the report text.
  readonly gaps = signal<GapItem[]>([]);
  readonly budget = signal<number | null>(null);
  readonly aiWritten = signal(false);

  // Real data from the backend, loaded by the pages that need it.
  readonly targets = signal<Target[]>([]);
  readonly selectedTargetId = signal('');
  readonly preview = signal<PreviewResponse | null>(null);
  private readonly previews = new Map<string, PreviewResponse>();

  readonly hasLiveSession = computed(() => !!this.sessionId() && !this.isExample());
  readonly recommendedTarget = computed(() => this.targets().find((t) => t.recommended) ?? null);
  readonly selectedTarget = computed(() => this.targets().find((t) => t.id === this.selectedTargetId()) ?? null);

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

  // A new report means new answers: the setup options and the files depend on them, so the cached ones are dropped.
  showReport(markdown: string, extra: { gaps?: GapItem[]; budget?: Budget; ai_written?: boolean } = {}): void {
    this.reportMarkdown.set(markdown);
    this.isExample.set(false);
    this.gaps.set(extra.gaps ?? []);
    this.budget.set(extra.budget?.monthly_eur ?? null);
    this.aiWritten.set(extra.ai_written ?? false);
    this.clearSetup();
  }

  private clearSetup(): void {
    this.targets.set([]);
    this.selectedTargetId.set('');
    this.preview.set(null);
    this.previews.clear();
  }

  async loadTargets(): Promise<void> {
    if (this.targets().length) return;
    const res = await this.api.targets(this.sessionId());
    this.targets.set(res.targets);
    if (!this.selectedTargetId()) {
      const rec = res.targets.find((t) => t.recommended) ?? res.targets[0];
      this.selectedTargetId.set(rec?.id ?? '');
    }
  }

  selectTarget(id: string): void {
    this.selectedTargetId.set(id);
  }

  // Loads the preview for the selected setup once per setup; the result is cached so flipping between pages costs nothing.
  async loadPreview(targetId: string): Promise<PreviewResponse> {
    const cached = this.previews.get(targetId);
    if (cached) {
      this.preview.set(cached);
      return cached;
    }
    const res = await this.api.preview(this.sessionId(), targetId || undefined);
    this.previews.set(targetId, res);
    this.preview.set(res);
    return res;
  }

  async openExample(): Promise<void> {
    const text = await this.api.example();
    this.reportMarkdown.set(text);
    this.isExample.set(true);
    this.gaps.set([]);
    this.budget.set(null);
    this.aiWritten.set(true);
    this.clearSetup();
    await this.router.navigate(['/report']);
  }

  startNewScan(): void {
    this.sessionId.set('');
    this.questions.set([]);
    this.answers.set({});
    this.reportMarkdown.set('');
    this.isExample.set(false);
    this.gaps.set([]);
    this.budget.set(null);
    this.aiWritten.set(false);
    this.clearSetup();
    this.router.navigate(['/scan']);
  }
}
