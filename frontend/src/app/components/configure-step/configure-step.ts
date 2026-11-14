import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ReportDataService } from '../../core/report-data.service';
import { WizardService } from '../../core/wizard.service';
import { errorMessage } from '../../core/api.service';
import { Target } from '../../models';
import { MoreInfoComponent } from '../more-info/more-info';
import { StepperComponent } from '../stepper/stepper';

@Component({
  selector: 'app-configure-step',
  imports: [RouterLink, StepperComponent, MoreInfoComponent],
  templateUrl: './configure-step.html',
})
export class ConfigureStepComponent implements OnInit {
  protected readonly wizard = inject(WizardService);
  protected readonly data = inject(ReportDataService);
  private readonly router = inject(Router);

  protected readonly loading = signal(true);
  protected readonly loadError = signal('');

  async ngOnInit(): Promise<void> {
    try {
      await this.wizard.loadTargets();
    } catch (e) {
      this.loadError.set(errorMessage(e, 'Could not load the options for this scan.'));
    } finally {
      this.loading.set(false);
    }
  }

  // The backend sets files=true for "not decided yet", but that option only gets the basic files.
  protected filesLabel(t: Target): string {
    if (t.id === 'not-yet' || !t.files) return 'Basic files only';
    return 'Infrastructure files included';
  }

  protected select(id: string): void {
    this.wizard.selectTarget(id);
  }

  protected preview(): void {
    this.router.navigate(['/files']);
  }
}
