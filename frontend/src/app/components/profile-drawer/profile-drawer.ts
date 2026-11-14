import { Component, ElementRef, HostListener, effect, inject, viewChild } from '@angular/core';
import { PROFILE } from '../../config';
import { ProfileService } from '../../core/profile.service';

@Component({
  selector: 'app-profile-drawer',
  templateUrl: './profile-drawer.html',
})
export class ProfileDrawerComponent {
  protected readonly profile = inject(ProfileService);
  protected readonly data = PROFILE;
  protected readonly initials = PROFILE.name
    .split(/\s+/)
    .map((w) => w.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
  private readonly closeBtn = viewChild<ElementRef<HTMLButtonElement>>('closeBtn');

  constructor() {
    effect(() => {
      if (this.profile.open()) queueMicrotask(() => this.closeBtn()?.nativeElement.focus());
    });
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.profile.close();
  }
}
