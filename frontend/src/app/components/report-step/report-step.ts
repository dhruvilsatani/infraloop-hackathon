import { Component, computed, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ProfileService } from '../../core/profile.service';
import { ReportDataService } from '../../core/report-data.service';
import { WizardService } from '../../core/wizard.service';
import { USE_MOCK_DATA } from '../../config';
import { StepperComponent } from '../stepper/stepper';

@Component({
  selector: 'app-report-step',
  imports: [StepperComponent],
  templateUrl: './report-step.html',
})
export class ReportStepComponent {
  protected readonly wizard = inject(WizardService);
  protected readonly data = inject(ReportDataService);
  protected readonly profile = inject(ProfileService);
  private readonly router = inject(Router);
  private readonly sanitizer = inject(DomSanitizer);
  protected readonly mock = USE_MOCK_DATA;

  protected readonly html = computed<SafeHtml>(() => {
    const md = this.wizard.reportMarkdown();
    if (!md) return '';
    const raw = marked.parse(md, { async: false }) as string;
    return this.sanitizer.bypassSecurityTrustHtml(DOMPurify.sanitize(raw));
  });

  protected back(): void {
    this.router.navigate([this.wizard.isExample() ? '/scan' : '/answer']);
  }

  protected continue(): void {
    this.router.navigate(['/configure']);
  }

  protected newScan(): void {
    this.wizard.startNewScan();
  }

  protected downloadMd(): void {
    this.download('md');
  }

  protected downloadJson(): void {
    this.download('json');
  }

  protected severityClass(severity: string): string {
    return 'sev sev-' + severity.toLowerCase();
  }

  private download(kind: 'md' | 'json'): void {
    const md = this.wizard.reportMarkdown();
    if (!md) return;
    const day = new Date().toISOString().slice(0, 10);
    const body =
      kind === 'json'
        ? JSON.stringify({ tool: 'InfraLoop', generated: day, format: 'markdown', report: md }, null, 2)
        : md;
    const url = URL.createObjectURL(new Blob([body], { type: kind === 'json' ? 'application/json' : 'text/markdown' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `infraloop-report-${day}.${kind}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
