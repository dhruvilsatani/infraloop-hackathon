import { Component, input } from '@angular/core';

@Component({
  selector: 'app-stepper',
  templateUrl: './stepper.html',
})
export class StepperComponent {
  readonly current = input.required<number>();
  protected readonly steps = ['Scan', 'Answer', 'Report', 'Configure', 'Files'];
}
