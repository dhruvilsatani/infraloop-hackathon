import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  readonly open = signal(false);
  private lastFocus: HTMLElement | null = null;

  show(): void {
    this.lastFocus = document.activeElement as HTMLElement | null;
    this.open.set(true);
  }

  close(): void {
    this.open.set(false);
    this.lastFocus?.focus?.();
  }
}
