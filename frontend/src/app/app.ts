import { Component, inject, viewChild } from '@angular/core';
import { BackgroundComponent } from './components/background/background';
import { ProfileDrawerComponent } from './components/profile-drawer/profile-drawer';
import { QuestionsStepComponent } from './components/questions-step/questions-step';
import { ReportStepComponent } from './components/report-step/report-step';
import { ScanStepComponent } from './components/scan-step/scan-step';
import { ProfileService } from './core/profile.service';
import { WizardService } from './core/wizard.service';
import { SHOWCASE } from './config';

@Component({
  selector: 'app-root',
  imports: [BackgroundComponent, ScanStepComponent, QuestionsStepComponent, ReportStepComponent, ProfileDrawerComponent],
  templateUrl: './app.html',
})
export class App {
  protected readonly wizard = inject(WizardService);
  protected readonly profile = inject(ProfileService);
  protected readonly showcase = SHOWCASE;
  private readonly scanStep = viewChild(ScanStepComponent);

  constructor() {
    // Showcase mode: a static always-on page that shows only the example report.
    if (this.showcase) {
      this.wizard.showExample().catch(() => undefined);
    }
  }

  protected startHere(e: Event): void {
    e.preventDefault();
    this.scanStep()?.focusRepo();
  }
}
