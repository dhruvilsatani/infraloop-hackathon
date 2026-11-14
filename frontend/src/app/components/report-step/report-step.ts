import { Component, computed, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ProfileService } from '../../core/profile.service';
import { WizardService } from '../../core/wizard.service';
import { SHOWCASE } from '../../config';

@Component({
  selector: 'app-report-step',
  templateUrl: './report-step.html',
})
export class ReportStepComponent {
  protected readonly wizard = inject(WizardService);
  protected readonly profile = inject(ProfileService);
  private readonly sanitizer = inject(DomSanitizer);
  protected readonly showcase = SHOWCASE;

  protected readonly html = computed<SafeHtml>(() => {
    const md = this.wizard.reportMarkdown();
    if (!md) return '';
    const raw = marked.parse(md, { async: false }) as string;
    return this.sanitizer.bypassSecurityTrustHtml(DOMPurify.sanitize(raw));
  });

  protected back(): void {
    this.wizard.backFromReport();
  }

  protected newScan(): void {
    window.location.reload();
  }

  protected downloadMd(): void {
    this.download('md');
  }

  protected downloadJson(): void {
    this.download('json');
  }

  // Example reports are not downloadable, matching the original page.
  private download(kind: 'md' | 'json'): void {
    const md = this.wizard.reportMarkdown();
    if (!md || this.wizard.isExample()) return;
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
