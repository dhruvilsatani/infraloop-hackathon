import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { WizardService } from './wizard.service';

// A user who opens /answer, /report, ... directly (or after a reload) has no data yet: send them to the scan.
export const hasSession: CanActivateFn = () =>
  inject(WizardService).sessionId() ? true : inject(Router).parseUrl('/scan');

export const hasReport: CanActivateFn = () =>
  inject(WizardService).reportMarkdown() ? true : inject(Router).parseUrl('/scan');
