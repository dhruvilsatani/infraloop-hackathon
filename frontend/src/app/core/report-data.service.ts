import { Injectable, computed, signal } from '@angular/core';
import {
  BASE_MONTHLY_COST,
  BUDGET_MONTHLY,
  CONFIG_GROUPS,
  ConfigGroup,
  DEFAULT_SELECTION,
  GAPS,
  GapItem,
  GeneratedFile,
  SETUP,
  SetupInfo,
  generateFiles,
} from '../mock/sample-data';

// Single entry point for the report, configure and files pages.
// Sample values come from mock/sample-data.ts until the backend returns them.
@Injectable({ providedIn: 'root' })
export class ReportDataService {
  readonly gaps: GapItem[] = GAPS;
  readonly setup: SetupInfo = SETUP;
  readonly configGroups: ConfigGroup[] = CONFIG_GROUPS;
  readonly baseCost = BASE_MONTHLY_COST;
  readonly budget = BUDGET_MONTHLY;

  private readonly allOptions = CONFIG_GROUPS.flatMap((g) => g.options);
  readonly selected = signal<Set<string>>(new Set(DEFAULT_SELECTION));

  readonly selectedOptions = computed(() => this.allOptions.filter((o) => this.selected().has(o.id)));
  readonly monthlyTotal = computed(() => this.baseCost + this.selectedOptions().reduce((n, o) => n + o.cost, 0));
  readonly recommendedTotal = computed(
    () => this.baseCost + this.allOptions.filter((o) => o.recommended).reduce((n, o) => n + o.cost, 0),
  );
  readonly files = computed<GeneratedFile[]>(() => generateFiles(this.selected()));

  toggle(id: string): void {
    this.selected.update((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
}
