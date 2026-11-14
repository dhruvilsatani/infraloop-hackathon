import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { WizardService } from '../../core/wizard.service';
import { Question } from '../../models';
import { QuestionsStepComponent } from './questions-step';

describe('QuestionsStepComponent suggestions', () => {
  it('fills a text answer from a chip and lets the user edit it', async () => {
    const questions = signal<Question[]>([
      { id: 'budget', question: 'Monthly infrastructure budget?', kind: 'text' },
      { id: 'custom', question: 'Anything else?', kind: 'text' },
      { id: 'uptime', question: 'How much downtime?', kind: 'choice', options: ['None', 'A few minutes'] },
      { id: 'database', question: 'The scan found database libraries. Tell us your production database details, storage, recovery window, and replica requirements. Example: PostgreSQL, managed by a cloud provider, 20 GB now and 60 GB in 12 months.', kind: 'text' },
    ]);
    const answers = signal<Record<string, string>>({});
    const wizard = {
      questions,
      answers,
      sessionId: signal('test-session'),
      setAnswer: (question: string, value: string) => answers.update((current) => ({ ...current, [question]: value })),
    };

    await TestBed.configureTestingModule({
      imports: [QuestionsStepComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: WizardService, useValue: wizard },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(QuestionsStepComponent);
    fixture.detectChanges();

    const budgetQuestion = fixture.nativeElement.querySelector('.q') as HTMLElement;
    const chip = budgetQuestion.querySelector('.suggestion-chip') as HTMLButtonElement;
    const input = budgetQuestion.querySelector('input[type="text"]') as HTMLInputElement;
    expect(budgetQuestion.querySelectorAll('.suggestion-chip').length).toBe(4);
    expect(budgetQuestion.querySelector('.required-mark')).not.toBeNull();
    expect(input.getAttribute('aria-required')).toBe('true');
    expect(fixture.nativeElement.querySelectorAll('.q')[1].querySelector('.suggestion-group')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.q')[2].querySelector('.suggestion-group')).toBeNull();

    const databaseQuestion = fixture.nativeElement.querySelectorAll('.q')[3] as HTMLElement;
    expect(databaseQuestion.querySelector('.field-label')?.textContent).toContain('Tell us about your production database');
    expect(databaseQuestion.querySelector('.question-details')?.textContent).toContain('replica requirements');
    expect(databaseQuestion.querySelector('.more-info-panel')?.getAttribute('aria-hidden')).toBe('true');
    const databaseChip = databaseQuestion.querySelector('.suggestion-chip') as HTMLButtonElement;
    databaseChip.click();
    fixture.detectChanges();
    expect(answers()[questions()[3].question]).toContain('PostgreSQL, managed by a cloud provider');

    chip.click();
    fixture.detectChanges();
    expect(input.value).toBe('€50 per month');
    expect(chip.getAttribute('aria-pressed')).toBe('true');

    input.value = 'My custom budget';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    expect(answers()['Monthly infrastructure budget?']).toBe('My custom budget');
    expect(chip.getAttribute('aria-pressed')).toBe('false');
  });
});
