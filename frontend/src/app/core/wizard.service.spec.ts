import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { ReportDataService } from './report-data.service';
import { WizardService } from './wizard.service';
import { Target } from '../models';

const target = { id: 'plan-0', recommended: true, monthly_eur: 30 } as Target;

describe('WizardService: a new report', () => {
  let wizard: WizardService;
  let data: ReportDataService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideRouter([])] });
    wizard = TestBed.inject(WizardService);
    data = TestBed.inject(ReportDataService);
  });

  it('drops the setup options of the previous answers, so they are loaded again', () => {
    wizard.targets.set([target]);
    wizard.selectTarget('plan-0');
    wizard.showReport('# report');
    expect(wizard.targets()).toEqual([]);
    expect(wizard.selectedTargetId()).toBe('');
    expect(wizard.preview()).toBeNull();
  });

  it('takes the gap list, the budget and the AI flag from the backend answer', () => {
    wizard.showReport('# report', {
      gaps: [{ name: 'No CI', severity: 'High', evidence: ['no workflow file'] }],
      budget: { monthly_eur: 50, status: 'fits' },
      ai_written: true,
    });
    expect(data.gaps().map((g) => g.name)).toEqual(['No CI']);
    expect(data.budget()).toBe(50);
    expect(data.isWithinBudget(30)).toBe(true);
    expect(data.isWithinBudget(60)).toBe(false);
    expect(wizard.aiWritten()).toBe(true);
  });

  it('compares with no budget when the user gave none', () => {
    wizard.showReport('# report', { budget: { monthly_eur: null, status: null } });
    expect(data.budget()).toBeNull();
    expect(data.isWithinBudget(10)).toBe(false);
  });
});
