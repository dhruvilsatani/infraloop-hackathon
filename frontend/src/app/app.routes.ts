import { Routes } from '@angular/router';
import { hasLiveSession, hasReport, hasSession } from './core/guards';
import { LandingComponent } from './components/landing/landing';
import { ScanStepComponent } from './components/scan-step/scan-step';
import { QuestionsStepComponent } from './components/questions-step/questions-step';
import { ReportStepComponent } from './components/report-step/report-step';
import { ConfigureStepComponent } from './components/configure-step/configure-step';
import { FilesStepComponent } from './components/files-step/files-step';

export const routes: Routes = [
  { path: '', component: LandingComponent, title: 'InfraLoop – production-readiness report for your repo' },
  { path: 'scan', component: ScanStepComponent, title: 'Analyze a repository · InfraLoop' },
  { path: 'answer', component: QuestionsStepComponent, canActivate: [hasSession], title: 'Answer · InfraLoop' },
  { path: 'report', component: ReportStepComponent, canActivate: [hasReport], title: 'Report · InfraLoop' },
  { path: 'configure', component: ConfigureStepComponent, canActivate: [hasLiveSession], title: 'Configure · InfraLoop' },
  { path: 'files', component: FilesStepComponent, canActivate: [hasLiveSession], title: 'Files · InfraLoop' },
  { path: '**', redirectTo: '' },
];
