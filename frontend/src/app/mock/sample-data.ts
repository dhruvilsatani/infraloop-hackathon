// SAMPLE DATA. These two values are not returned by the backend yet. Replace them when it does;
// the pages read them through ReportDataService and do not need to change.
//
// Still missing from the API (for the backend developer):
//   1. The gap list: name, severity and evidence for each gap. Only advice titles and skip reasons are returned today.
//   2. The budget comparison: the budget the user gave and whether the recommended setup fits it.

export type Severity = 'High' | 'Medium' | 'Low';

export interface GapItem {
  name: string;
  severity: Severity;
  evidence: string[];
}

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
