import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { QuestionPreset, questionPresets } from '../../core/question-presets';
import { WizardService } from '../../core/wizard.service';
import { normalizeQuestion, Question } from '../../models';
import { MoreInfoComponent } from '../more-info/more-info';
import { StepperComponent } from '../stepper/stepper';

@Component({
  selector: 'app-questions-step',
  imports: [FormsModule, StepperComponent, MoreInfoComponent],
  templateUrl: './questions-step.html',
})
export class QuestionsStepComponent {
  protected readonly wizard = inject(WizardService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  protected offline = false;
  protected readonly busy = signal(false);
  protected readonly error = signal('');
  // soft check: the report is generic without these; warn once, then let the user go on
  private warned = false;

  protected readonly visibleQuestions = computed(() => this.wizard.questions().filter((q) => this.isVisible(q)));

  protected answer(q: Question): string {
    return this.wizard.answers()[q.question] ?? '';
  }

  protected presetsFor(q: Question): readonly QuestionPreset[] {
    return q.kind !== 'choice' ? questionPresets(q.id) : [];
  }

  protected choosePreset(q: Question, preset: QuestionPreset): void {
    this.wizard.setAnswer(q.question, preset.value);
  }

  protected questionTitle(q: Question): string {
    return q.id === 'database' ? 'Tell us about your production database' : q.question;
  }

  protected hasLongDetails(q: Question): boolean {
    return q.id === 'database';
  }

  protected onText(q: Question, e: Event): void {
    this.wizard.setAnswer(q.question, (e.target as HTMLInputElement).value);
  }

  protected isVisible(q: Question): boolean {
    if (!q.depends_on) return true;
    const parent = this.wizard.questions().find((p) => p.id === q.depends_on?.id);
    if (!parent || parent.kind !== 'choice') return false;
    const value = this.wizard.answers()[parent.question];
    return !!value && value !== q.depends_on.not;
  }

  protected async submit(): Promise<void> {
    const answers: Record<string, string> = {};
    for (const q of this.visibleQuestions()) {
      const value = this.answer(q).trim();
      if (value) answers[q.question] = value;
    }

    this.error.set('');
    const missing: string[] = [];
    for (const q of this.visibleQuestions()) {
      const text = q.question.toLowerCase();
      if (answers[q.question]) continue;
      if (text.includes('budget')) missing.push('budget');
      else if (text.includes('your database')) missing.push('database');
      else if (text.includes('downtime')) missing.push('downtime');
    }
    if (missing.length && !this.warned) {
      this.warned = true;
      this.error.set(
        `Not answered: ${missing.join(', ')}. Without these the report stays generic (no budget check, no database advice). Press Generate report again to continue anyway.`,
      );
      return;
    }

    this.busy.set(true);
    try {
      const res = await this.api.answer(this.wizard.sessionId(), answers, this.offline ? 'offline' : '');
      if (res.status === 'need_more_info') {
        this.wizard.setQuestions(res.questions.map(normalizeQuestion));
      } else {
        this.wizard.showReport(res.report, res);
        await this.router.navigate(['/report']);
      }
    } catch (e) {
      this.error.set(errorMessage(e, 'Report generation failed'));
    } finally {
      this.busy.set(false);
    }
  }
}
