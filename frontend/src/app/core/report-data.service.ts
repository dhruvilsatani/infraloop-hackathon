import { Injectable, computed, inject } from '@angular/core';
import { USE_MOCK_DATA } from '../config';
import { BUDGET_MONTHLY, GAPS } from '../mock/sample-data';
import { GapItem, Target } from '../models';
import { WizardService } from './wizard.service';

// Maps backend results to what the pages show. With USE_MOCK_DATA the gap list and the budget are sample data instead.
@Injectable({ providedIn: 'root' })
export class ReportDataService {
  private readonly wizard = inject(WizardService);

  readonly mock = USE_MOCK_DATA;
  readonly gaps = computed<GapItem[]>(() => (USE_MOCK_DATA ? GAPS : this.wizard.gaps()));
  // null = the user gave no usable budget, so there is nothing to compare with.
  readonly budget = computed<number | null>(() => (USE_MOCK_DATA ? BUDGET_MONTHLY : this.wizard.budget()));
  readonly recommended = this.wizard.recommendedTarget;
  readonly selected = this.wizard.selectedTarget;
  readonly targets = this.wizard.targets;

  // Priced options the user did not pick, shown as "alternatives you did not pick".
  readonly alternatives = computed<Target[]>(() =>
    this.wizard.targets().filter((t) => !t.recommended && t.monthly_eur !== null),
  );

  isWithinBudget(cost: number | null | undefined): boolean {
    const budget = this.budget();
    return budget !== null && cost !== null && cost !== undefined && cost <= budget;
  }
}
