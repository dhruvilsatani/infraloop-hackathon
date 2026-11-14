// SAMPLE DATA, used only when USE_MOCK_DATA (config.ts) is true, and for the example card on the landing page.
// The real gap list and budget come from the backend (POST /answer).
import { GapItem } from '../models';

export const BUDGET_MONTHLY = 150;

export const GAPS: GapItem[] = [
  {
    name: 'Tests',
    severity: 'High',
    evidence: ['No test files found in 6 of 9 services.', 'The CI configuration has no test step.'],
  },
  {
    name: 'CI',
    severity: 'Medium',
    evidence: ['Builds and deploys are run by hand; no workflow file was found.'],
  },
  {
    name: 'Backups',
    severity: 'High',
    evidence: ['The database has no snapshot schedule or retention rule.'],
  },
  {
    name: 'Monitoring',
    severity: 'Medium',
    evidence: ['No metrics endpoint and no alert rules found.'],
  },
  {
    name: 'Secrets',
    severity: 'Low',
    evidence: ['Keys are read from environment variables; no secret manager is configured.'],
  },
];
