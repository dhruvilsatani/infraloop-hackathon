import { Component, ElementRef, HostListener, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { UploadService, MAX_FILES_CLIENT } from '../../core/upload.service';
import { WizardService } from '../../core/wizard.service';
import { normalizeQuestion } from '../../models';
import { StepperComponent } from '../stepper/stepper';

@Component({
  selector: 'app-scan-step',
  imports: [FormsModule, StepperComponent],
  templateUrl: './scan-step.html',
})
export class ScanStepComponent {
  protected readonly upload = inject(UploadService);
  private readonly api = inject(ApiService);
  private readonly wizard = inject(WizardService);
  private readonly router = inject(Router);

  protected readonly maxFiles = MAX_FILES_CLIENT;
  protected repo = '';
  protected notes = '';
  protected readonly busy = signal(false);
  protected readonly status = signal('Scanning repository structure…');
  protected readonly error = signal('');
  protected readonly dragOver = signal(false);

  private readonly repoInput = viewChild.required<ElementRef<HTMLInputElement>>('repoInput');
  private readonly folderInput = viewChild.required<ElementRef<HTMLInputElement>>('folderInput');

  // Dropping a folder anywhere on the page must not make the browser open the files.
  @HostListener('window:dragover', ['$event'])
  @HostListener('window:drop', ['$event'])
  protected preventWindowDrop(e: Event): void {
    e.preventDefault();
  }

  focusRepo(): void {
    this.repoInput().nativeElement.focus();
  }

  protected onFolderChosen(e: Event): void {
    this.upload.pickFromInput((e.target as HTMLInputElement).files);
  }

  protected onDragOver(e: DragEvent): void {
    e.preventDefault();
    this.dragOver.set(true);
  }

  protected onDragLeave(e: DragEvent): void {
    e.preventDefault();
    this.dragOver.set(false);
  }

  protected onDrop(e: DragEvent): void {
    e.preventDefault();
    this.dragOver.set(false);
    if (!e.dataTransfer) return;
    this.upload.pickFromDrop(e.dataTransfer).catch((err: unknown) => {
      this.error.set('Could not read that folder: ' + errorMessage(err, String(err)));
    });
  }

  protected clearFolder(): void {
    this.upload.clear();
    this.folderInput().nativeElement.value = '';
  }

  protected async analyze(): Promise<void> {
    const repo = this.repo.trim();
    const picked = this.upload.picked();
    this.error.set('');
    if (!repo && !picked) {
      this.error.set('Paste a repository link or path, or choose your project folder.');
      return;
    }

    this.busy.set(true);
    this.status.set('Scanning repository structure…');
    try {
      let uploadId = '';
      if (picked) {
        this.status.set('Uploading project…');
        uploadId = await this.upload.upload((text) => this.status.set(text));
        this.status.set('Scanning project structure…');
      }
      const res = await this.api.scan(picked ? '' : repo, uploadId, this.notes);
      this.wizard.startQuestions(res.session_id, res.questions.map(normalizeQuestion));
      await this.router.navigate(['/answer']);
    } catch (e) {
      this.error.set(errorMessage(e, 'Scan failed'));
    } finally {
      this.busy.set(false);
    }
  }

  protected async example(): Promise<void> {
    this.error.set('');
    try {
      await this.wizard.openExample();
    } catch {
      this.error.set('Could not load the example report.');
    }
  }
}
