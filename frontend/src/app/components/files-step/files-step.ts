import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { strToU8, zipSync } from 'fflate';
import { WizardService } from '../../core/wizard.service';
import { errorMessage } from '../../core/api.service';
import { StepperComponent } from '../stepper/stepper';

// One row in the file tree: a guide (SETUP/IMPLEMENTATION/MANIFEST) or a generated file.
interface FileItem {
  path: string;
  title: string;
  content: string;
  folder: string;
  kind: 'guide' | 'basic' | 'cloud';
}

interface FolderGroup {
  folder: string;
  items: FileItem[];
}

const GUIDES = 'Guides';

@Component({
  selector: 'app-files-step',
  imports: [RouterLink, StepperComponent],
  templateUrl: './files-step.html',
})
export class FilesStepComponent implements OnInit {
  protected readonly wizard = inject(WizardService);

  protected readonly loading = signal(true);
  protected readonly loadError = signal('');

  // Edits are kept per path; a file counts as edited only when its text differs from the generated text.
  protected readonly edits = signal<Record<string, string>>({});
  protected readonly excluded = signal<Set<string>>(new Set());
  protected readonly openTabs = signal<string[]>([]);
  protected readonly active = signal('');

  protected readonly items = computed<FileItem[]>(() => {
    const p = this.wizard.preview();
    if (!p) return [];
    const guides: FileItem[] = p.docs.map((d) => ({ path: d.path, title: d.title, content: d.content, folder: GUIDES, kind: 'guide' }));
    const files: FileItem[] = p.files.map((f) => ({
      path: f.path,
      title: f.title,
      content: f.content,
      folder: f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : '',
      kind: f.group,
    }));
    return [...guides, ...files];
  });

  protected readonly groups = computed<FolderGroup[]>(() => {
    const byFolder = new Map<string, FileItem[]>();
    for (const item of this.items()) {
      const list = byFolder.get(item.folder) ?? [];
      list.push(item);
      byFolder.set(item.folder, list);
    }
    return [...byFolder.entries()].map(([folder, items]) => ({ folder, items }));
  });

  protected readonly includedCount = computed(() => this.items().filter((i) => !this.excluded().has(i.path)).length);
  protected readonly activeItem = computed(() => this.items().find((i) => i.path === this.active()) ?? null);
  protected readonly activeContent = computed(() => this.content(this.active()));
  protected readonly lines = computed(() => {
    const count = this.activeContent().split('\n').length;
    return Array.from({ length: count }, (_, i) => i + 1);
  });

  async ngOnInit(): Promise<void> {
    try {
      const preview = await this.wizard.loadPreview(this.wizard.selectedTargetId());
      const first = preview.docs[0]?.path ?? preview.files[0]?.path ?? '';
      this.openTabs.set(first ? [first] : []);
      this.active.set(first);
    } catch (e) {
      this.loadError.set(errorMessage(e, 'Could not load the files for this scan.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected basename(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1);
  }

  protected original(path: string): string {
    return this.items().find((i) => i.path === path)?.content ?? '';
  }

  protected content(path: string): string {
    return this.edits()[path] ?? this.original(path);
  }

  protected isEdited(path: string): boolean {
    return path in this.edits() && this.edits()[path] !== this.original(path);
  }

  protected isIncluded(path: string): boolean {
    return !this.excluded().has(path);
  }

  protected toggleIncluded(path: string): void {
    this.excluded.update((set) => {
      const next = new Set(set);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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
    this.saveBlob(new Blob([this.activeContent()], { type: 'text/plain' }), this.basename(this.active()));
  }

  // Zip of the included items only, with any edits applied.
  protected downloadAll(): void {
    const archive: Record<string, Uint8Array> = {};
    for (const item of this.items()) {
      if (this.isIncluded(item.path)) archive[item.path] = strToU8(this.content(item.path));
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
