import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ProfileService } from '../../core/profile.service';
import { ReportDataService } from '../../core/report-data.service';
import { WizardService } from '../../core/wizard.service';
import { USE_MOCK_DATA } from '../../config';

@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  templateUrl: './landing.html',
})
export class LandingComponent {
  protected readonly data = inject(ReportDataService);
  protected readonly profile = inject(ProfileService);
  protected readonly wizard = inject(WizardService);
  protected readonly mock = USE_MOCK_DATA;

  protected readonly trust = [
    'Evidence for every finding',
    'Cost calculated in code',
    'Secret files never uploaded',
    'Report only, no cloud access',
  ];

  protected readonly flow = ['Your repository', 'Scan', 'Short summary', 'AI model'];

  protected openExample(e: Event): void {
    e.preventDefault();
    this.wizard.openExample().catch(() => undefined);
  }
}
