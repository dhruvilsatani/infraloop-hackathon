import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';
import { WizardService } from '../../core/wizard.service';

@Component({
  selector: 'app-site-header',
  imports: [RouterLink],
  templateUrl: './site-header.html',
})
export class SiteHeaderComponent {
  private readonly router = inject(Router);
  protected readonly wizard = inject(WizardService);

  protected readonly onLanding = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.router.url.split(/[?#]/)[0] === '/'),
    ),
    { initialValue: this.router.url.split(/[?#]/)[0] === '/' },
  );

  protected openExample(e: Event): void {
    e.preventDefault();
    this.wizard.openExample().catch(() => undefined);
  }

  protected newScan(e: Event): void {
    e.preventDefault();
    this.wizard.startNewScan();
  }
}
