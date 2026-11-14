import { Component, input, signal } from '@angular/core';

@Component({
  selector: 'app-more-info',
  templateUrl: './more-info.html',
})
export class MoreInfoComponent {
  private static nextId = 0;

  readonly title = input('');
  protected readonly expanded = signal(false);
  protected readonly panelId = `more-info-panel-${MoreInfoComponent.nextId++}`;

  protected toggle(): void {
    this.expanded.update((value) => !value);
  }
}
