import { Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { ReportDataService } from '../../core/report-data.service';
import { USE_MOCK_DATA } from '../../config';
import { StepperComponent } from '../stepper/stepper';

@Component({
  selector: 'app-configure-step',
  imports: [StepperComponent],
  templateUrl: './configure-step.html',
})
export class ConfigureStepComponent {
  protected readonly data = inject(ReportDataService);
  private readonly router = inject(Router);
  protected readonly mock = USE_MOCK_DATA;

  protected readonly withinBudget = computed(() => this.data.monthlyTotal() <= this.data.budget);

  protected isOn(id: string): boolean {
    return this.data.selected().has(id);
  }

  protected toggle(id: string): void {
    this.data.toggle(id);
  }

  protected preview(): void {
    this.router.navigate(['/files']);
  }
}
