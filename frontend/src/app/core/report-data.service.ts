import { Injectable, computed, inject } from '@angular/core';
import { BUDGET_MONTHLY, GAPS, GapItem } from '../mock/sample-data';
import { Target } from '../models';
import { WizardService } from './wizard.service';

// Maps backend results to what the pages show. The gap table and the budget are still sample data (see mock/sample-data.ts).
@Injectable({ providedIn: 'root' })
export class ReportDataService {
  private readonly wizard = inject(WizardService);

  readonly gaps: GapItem[] = GAPS;
  readonly budget = BUDGET_MONTHLY;
  readonly recommended = this.wizard.recommendedTarget;
  readonly selected = this.wizard.selectedTarget;
  readonly targets = this.wizard.targets;

  // Priced options the user did not pick, shown as "alternatives you did not pick".
  readonly alternatives = computed<Target[]>(() =>
    this.wizard.targets().filter((t) => !t.recommended && t.monthly_eur !== null),
  );

  isWithinBudget(cost: number | null | undefined): boolean {
    return cost !== null && cost !== undefined && cost <= this.budget;
  }
}
