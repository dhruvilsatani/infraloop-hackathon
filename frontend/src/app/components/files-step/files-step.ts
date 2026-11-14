import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { strToU8, zipSync } from 'fflate';
import { ReportDataService } from '../../core/report-data.service';
import { GeneratedFile } from '../../mock/sample-data';
import { USE_MOCK_DATA } from '../../config';
import { StepperComponent } from '../stepper/stepper';

interface FolderGroup {
  folder: string;
  files: GeneratedFile[];
}

@Component({
  selector: 'app-files-step',
  imports: [RouterLink, StepperComponent],
  templateUrl: './files-step.html',
})
export class FilesStepComponent {
  private readonly data = inject(ReportDataService);
  protected readonly mock = USE_MOCK_DATA;

  protected readonly files = this.data.files;
  protected readonly groups = computed<FolderGroup[]>(() => {
    const byFolder = new Map<string, GeneratedFile[]>();
    for (const f of this.files()) {
      const list = byFolder.get(f.folder) ?? [];
      list.push(f);
      byFolder.set(f.folder, list);
    }
    return [...byFolder.entries()].map(([folder, items]) => ({ folder, files: items }));
  });

  // Edits are kept per file path. A file counts as edited only when its text differs from the generated text.
  protected readonly edits = signal<Record<string, string>>({});
  protected readonly openTabs = signal<string[]>([]);
  protected readonly active = signal('');

  protected readonly activeContent = computed(() => this.content(this.active()));
  protected readonly lines = computed(() => {
    const count = this.activeContent().split('\n').length;
    return Array.from({ length: count }, (_, i) => i + 1);
  });

  constructor() {
    const first = this.files()[0]?.path ?? '';
    this.openTabs.set(first ? [first] : []);
    this.active.set(first);
  }

  protected basename(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1);
  }

  protected original(path: string): string {
    return this.files().find((f) => f.path === path)?.content ?? '';
  }

  protected content(path: string): string {
    return this.edits()[path] ?? this.original(path);
  }

  protected isEdited(path: string): boolean {
    return path in this.edits() && this.edits()[path] !== this.original(path);
  }

  protected anyEdited(): boolean {
    return this.files().some((f) => this.isEdited(f.path));
  }

  protected openFile(path: string): void {
    if (!this.openTabs().includes(path)) this.openTabs.update((t) => [...t, path]);
    this.active.set(path);
  }

  protected onEdit(e: Event): void {
    const value = (e.target as HTMLTextAreaElement).value;
    const path = this.active();
    this.edits.update((edits) => ({ ...edits, [path]: value }));
  }

  protected resetActive(): void {
    const path = this.active();
    this.edits.update((edits) => {
      const next = { ...edits };
      delete next[path];
      return next;
    });
  }

  protected async copyActive(): Promise<void> {
    await navigator.clipboard?.writeText(this.activeContent());
  }

  protected downloadActive(): void {
    const path = this.active();
    this.saveBlob(new Blob([this.activeContent()], { type: 'text/plain' }), this.basename(path));
  }

  protected downloadAll(): void {
    const archive: Record<string, Uint8Array> = {};
    for (const f of this.files()) {
      archive[f.path] = strToU8(this.content(f.path));
    }
    const zipped = zipSync(archive);
    this.saveBlob(new Blob([zipped as BlobPart], { type: 'application/zip' }), 'infraloop-files.zip');
  }

  private saveBlob(blob: Blob, name: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
