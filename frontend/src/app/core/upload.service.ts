import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService, errorMessage } from './api.service';
import { FileKind, PickedFolder, UploadFile } from '../models';

// Mirrors uploads.py and the original index.html; the server re-checks everything.
export const MAX_FILES_CLIENT = 100000;
const SKIP_DIRS = new Set([
  '.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox',
  '.next', '.nuxt', '.svelte-kit', '.gradle', '.terraform', '.idea', '.cache', 'bower_components', 'Pods',
  '.dart_tool', 'target', 'dist', 'coverage', 'vendor', '.parcel-cache', '.turbo', '.yarn', '.pnpm-store', 'site-packages',
]);
const BINARY_EXT = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg', '.pdf', '.zip', '.gz', '.tgz', '.tar', '.bz2',
  '.xz', '.7z', '.rar', '.jar', '.war', '.class', '.so', '.dll', '.dylib', '.exe', '.bin', '.o', '.a', '.pyc',
  '.woff', '.woff2', '.ttf', '.otf', '.eot', '.mp3', '.mp4', '.mov', '.avi', '.wav', '.webm', '.onnx', '.pt', '.pth',
  '.h5', '.pkl', '.parquet', '.sqlite', '.db', '.dmp', '.iso', '.dmg', '.pptx', '.docx', '.xlsx',
]);
const SECRET_RE = /^(\.env(\..+)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|.*\.jks|.*\.keystore|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|\.npmrc|\.pypirc|\.netrc|credentials(\.json)?|service[-_]account.*\.json|.*\.tfvars|secrets?\.(ya?ml|json|toml)|.*\.kdbx)$/i;
const SECRET_OK_RE = /\.(example|sample|template|dist|defaults?)$/i;
const CONFIG_RE = /(^|\/)(dockerfile[^\/]*|docker-compose[^\/]*|compose\.ya?ml|makefile|jenkinsfile|package\.json|pyproject\.toml|requirements[^\/]*\.txt|go\.mod|pom\.xml|build\.gradle(\.kts)?|cargo\.toml|gemfile|composer\.json|chart\.ya?ml|values[^\/]*\.ya?ml|readme[^\/]*)$|\.(ya?ml|tf|tfvars|toml|ini|cfg|conf|properties|hcl|gradle|json)$/i;
const MAX_FILE = 1024 * 1024;
const TEXT_BUDGET = 100 * 1024 * 1024;
const BATCH_FILES = 300;
const BATCH_BYTES = 3 * 1024 * 1024;
const MAX_DEPTH = 40;

export type Classification = { kind: 'skip'; dir: string } | { kind: FileKind; secret: boolean };

export function classifyFile(relPath: string, size: number): Classification {
  const parts = relPath.split('/');
  const hit = parts.slice(0, -1).find((p) => SKIP_DIRS.has(p));
  if (hit) return { kind: 'skip', dir: hit };
  const name = parts[parts.length - 1];
  if (SECRET_RE.test(name) && !SECRET_OK_RE.test(name)) return { kind: 'placeholder', secret: true };
  const dot = name.lastIndexOf('.');
  const ext = dot > 0 ? name.slice(dot).toLowerCase() : '';
  if (BINARY_EXT.has(ext) || size > MAX_FILE) return { kind: 'placeholder', secret: false };
  return { kind: 'send', secret: false };
}

export function newPick(root: string): PickedFolder {
  return { root, files: [], skipped: {}, secrets: [], bytes: 0, tooMany: false };
}

export function addToPick(p: PickedFolder, fullPath: string, file: File): void {
  const parts = fullPath.split('/');
  const inside = parts.slice(1).join('/');
  if (!inside) return;
  const c = classifyFile(inside, file.size);
  if (c.kind === 'skip') {
    p.skipped[c.dir] = (p.skipped[c.dir] || 0) + 1;
    return;
  }
  if (p.files.length >= MAX_FILES_CLIENT) {
    p.tooMany = true;
    return;
  }
  if (c.secret) p.secrets.push(parts[parts.length - 1]);
  if (c.kind === 'send') p.bytes += file.size;
  p.files.push({ path: fullPath, file, kind: c.kind });
}

export function fmtMB(b: number): string {
  return (b / 1048576).toFixed(b < 1048576 * 10 ? 1 : 0) + ' MB';
}

async function readAll(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = [];
  while (true) {
    const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) break;
    all.push(...batch);
  }
  return all;
}

async function walkEntry(entry: FileSystemEntry, p: PickedFolder, depth: number): Promise<void> {
  if (p.files.length >= MAX_FILES_CLIENT) {
    p.tooMany = true;
    return;
  }
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    addToPick(p, entry.fullPath.replace(/^\//, ''), file);
  } else if (entry.isDirectory && depth < MAX_DEPTH) {
    const dir = entry as FileSystemDirectoryEntry;
    if (depth > 0 && SKIP_DIRS.has(dir.name)) {
      p.skipped[dir.name] = (p.skipped[dir.name] || 0) + 1;
      return;
    }
    for (const child of await readAll(dir.createReader())) {
      await walkEntry(child, p, depth + 1);
    }
  }
}

@Injectable({ providedIn: 'root' })
export class UploadService {
  private readonly api = inject(ApiService);

  readonly picked = signal<PickedFolder | null>(null);
  readonly notice = signal('');
  readonly reading = signal(false);

  readonly summary = computed(() => {
    const p = this.picked();
    if (!p) return null;
    return {
      root: p.root,
      sent: p.files.filter((f) => f.kind === 'send').length,
      size: fmtMB(p.bytes),
      skipped: Object.entries(p.skipped)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([d, n]) => (n > 1 ? `${d} (${n} files)` : d)),
      secrets: [...new Set(p.secrets)].slice(0, 6),
      tooMany: p.tooMany,
    };
  });

  pickFromInput(files: FileList | null): void {
    if (!files || !files.length) return;
    const first = files[0].webkitRelativePath || files[0].name;
    const p = newPick(first.split('/')[0]);
    for (const f of Array.from(files)) {
      addToPick(p, f.webkitRelativePath || f.name, f);
    }
    this.setPicked(p);
  }

  async pickFromDrop(dt: DataTransfer): Promise<void> {
    const entry = Array.from(dt.items)
      .map((i) => i.webkitGetAsEntry?.())
      .find((e): e is FileSystemDirectoryEntry => !!e && e.isDirectory);
    if (!entry) throw new Error('Please drop a folder, not a single file.');
    const p = newPick(entry.name);
    this.reading.set(true);
    try {
      await walkEntry(entry, p, 0);
      this.setPicked(p);
    } finally {
      this.reading.set(false);
    }
  }

  clear(): void {
    this.picked.set(null);
    this.notice.set('');
  }

  // Very large project: keep config/infra files in full, send only the names of the biggest source files.
  private fitToBudget(p: PickedFolder): number {
    let total = p.files.reduce((n, f) => n + (f.kind === 'send' ? f.file.size : 0), 0);
    if (total <= TEXT_BUDGET) return 0;
    const code = p.files
      .filter((f) => f.kind === 'send' && !CONFIG_RE.test(f.path))
      .sort((a, b) => b.file.size - a.file.size);
    let trimmed = 0;
    for (const f of code) {
      if (total <= TEXT_BUDGET) break;
      total -= f.file.size;
      f.kind = 'placeholder';
      trimmed++;
    }
    return trimmed;
  }

  // Returns the upload_id to pass to /scan.
  async upload(onStatus: (text: string) => void): Promise<string> {
    const p = this.picked();
    if (!p) throw new Error('No folder selected');
    const trimmed = this.fitToBudget(p);
    if (trimmed) onStatus(`Large project: ${trimmed} of the biggest source files are sent by name only…`);

    let uploadId: string;
    try {
      uploadId = (await this.api.startUpload()).upload_id;
    } catch (e) {
      throw new Error(errorMessage(e, 'Could not start the upload'));
    }

    let batch: UploadFile[] = [];
    let batchBytes = 0;
    let done = 0;
    const total = p.files.length;
    const flush = async (): Promise<void> => {
      if (!batch.length) return;
      try {
        await this.api.uploadFiles(uploadId, batch);
      } catch (e) {
        throw new Error(errorMessage(e, 'Upload failed'));
      }
      done += batch.length;
      batch = [];
      batchBytes = 0;
      onStatus(`Uploading project… ${done} / ${total} files`);
    };

    for (const f of p.files) {
      const text = f.kind === 'send' ? await f.file.text() : '';
      batch.push({ path: f.path, text });
      batchBytes += text.length;
      if (batch.length >= BATCH_FILES || batchBytes > BATCH_BYTES) await flush();
    }
    await flush();
    return uploadId;
  }

  private setPicked(p: PickedFolder): void {
    if (!p.files.length) {
      this.picked.set(null);
      this.notice.set('No usable files found in that folder.');
      return;
    }
    this.notice.set('');
    this.picked.set(p);
  }
}
