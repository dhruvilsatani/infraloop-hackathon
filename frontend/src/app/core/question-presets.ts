export interface QuestionPreset {
  label: string;
  value: string;
}

// Suggested answers are keyed by the stable question id, not its display text.
// They are optional shortcuts: users can always replace them with a custom answer.
const PRESETS: Record<string, QuestionPreset[]> = {
  budget: [
    { label: '€50 / month', value: '€50 per month' },
    { label: '€100 / month', value: '€100 per month' },
    { label: '€250 / month', value: '€250 per month' },
    { label: 'Not sure yet', value: "I don't know yet" },
  ],
  traffic_start: [
    { label: 'Small launch', value: 'About 1,000 monthly active users at launch' },
    { label: 'Growing service', value: 'About 10,000 monthly active users' },
    { label: 'Requests-based', value: 'About 50,000 requests per day' },
    { label: 'Not sure yet', value: "Don't know" },
  ],
  database: [
    {
      label: 'Managed PostgreSQL',
      value: 'PostgreSQL, managed by a cloud provider, 20 GB now and 60 GB in 12 months, a few minutes of lost data is acceptable, no replicas.',
    },
    {
      label: 'Self-managed PostgreSQL',
      value: 'PostgreSQL, run it myself on a server, 20 GB now and 60 GB in 12 months, a few minutes of lost data is acceptable, no replicas.',
    },
    { label: 'No production database', value: 'No database in production.' },
    { label: 'Not sure yet', value: "I don't know yet; please state assumptions rather than guess." },
  ],
  region: [
    { label: 'Europe / EU residency', value: 'Mainly Europe; EU/GDPR data residency is required.' },
    { label: 'North America', value: 'Mainly North America; no specific data residency requirement.' },
    { label: 'Global users', value: 'Users are global; no additional data residency requirements.' },
    { label: 'Not sure yet', value: "I don't know yet." },
  ],
  deploy_frequency: [
    { label: 'Daily', value: 'Daily' },
    { label: 'Weekly', value: 'Weekly' },
    { label: 'Rarely', value: 'Rarely' },
  ],
  focus: [
    { label: 'Security', value: 'Focus on security and secrets management.' },
    { label: 'Reliability', value: 'Focus on reliability, backups, and recovery.' },
    { label: 'Cost', value: 'Focus on keeping infrastructure costs low.' },
    { label: 'Release process', value: 'Focus on CI/CD and the release process.' },
  ],
  real_traffic: [
    { label: 'Low and steady', value: 'Low and steady traffic, without large peaks.' },
    { label: 'Growing', value: 'Moderate traffic that is growing steadily.' },
    { label: 'Spiky', value: 'Traffic can have short, unpredictable peaks.' },
    { label: 'Not sure', value: "I don't know; traffic measurements are not available yet." },
  ],
  where_running: [
    { label: 'AWS', value: 'AWS; please confirm the region and deployment method.' },
    { label: 'Azure', value: 'Azure; please confirm the region and deployment method.' },
    { label: 'Google Cloud', value: 'Google Cloud; please confirm the region and deployment method.' },
    { label: 'Self-hosted', value: 'Self-hosted server or cluster; provider and region to be confirmed.' },
    { label: 'Not launched yet', value: 'Not launched yet.' },
  ],
  existing_infra_notes: [
    { label: 'No major issues', value: 'No major issues; looking for a production-readiness baseline.' },
    { label: 'Reliability', value: 'Reliability and reducing outages are the main concerns.' },
    { label: 'Cost', value: 'Infrastructure cost is the main concern.' },
    { label: 'Deployments', value: 'Making deployments safer and easier is the main concern.' },
  ],
  which_service: [
    { label: 'All services', value: 'Analyze all services.' },
    { label: 'API / backend', value: 'Focus on the API or backend service; I will confirm its exact name.' },
    { label: 'Web app', value: 'Focus on the frontend or web app; I will confirm its exact name.' },
  ],
  managed_backend: [
    { label: 'Free tier', value: 'Upstash free tier; please verify plan limits and whether built-in backups and scaling are enabled.' },
    { label: 'Paid tier', value: 'Upstash paid production tier; exact plan and built-in backup/scaling settings need confirmation.' },
    { label: 'Not sure of the plan', value: "I don't know the Upstash plan or tier; please call out what I should verify about backups and scaling." },
  ],
  paas: [
    { label: 'Stay on this platform', value: 'Plan to stay on the current platform.' },
    { label: 'Move to our cloud', value: 'Plan to move to our own cloud account.' },
    { label: 'Not decided yet', value: 'Not decided yet; compare staying with moving.' },
  ],
  model_usage: [
    { label: 'Low-volume online', value: 'Online model serving, starting at roughly 100 requests per day; model choice is not final.' },
    { label: 'Batch jobs', value: 'Batch inference jobs, starting at roughly 100 jobs per day; model choice is not final.' },
    { label: 'Not sure yet', value: "I don't know the model or volume yet; please state the assumptions used." },
  ],
  spikes: [
    { label: 'No major campaign', value: 'No major launch or campaign is planned in the next 12 months.' },
    { label: 'Product launch', value: 'A product launch is planned; traffic may increase temporarily.' },
    { label: 'Seasonal campaign', value: 'Seasonal or marketing campaigns may cause temporary traffic peaks.' },
  ],
  current_cost: [
    { label: 'Under €50', value: 'Under €50 per month' },
    { label: '€50–€250', value: 'About €50–€250 per month' },
    { label: 'Over €250', value: 'Over €250 per month' },
    { label: 'Not sure', value: "I don't know the current monthly cost." },
  ],
  environments: [
    { label: 'Dev, staging, production', value: 'Development, staging, and production' },
    { label: 'Production only', value: 'Production only' },
    { label: 'Dev and production', value: 'Development and production; no staging environment' },
  ],
  deployment_status: [
    { label: 'Not launched yet', value: 'Not launched yet' },
    { label: 'Staging only', value: 'Applied in staging only' },
    { label: 'In production', value: 'Already applied in production' },
  ],
  payment_compliance: [
    { label: 'Hosted checkout', value: 'Only the payment provider handles card data through hosted checkout.' },
    { label: 'Handle card data', value: 'The application handles card data directly.' },
    { label: 'Not sure', value: "I'm not sure yet; please flag the compliance implications." },
  ],
  ml_serving: [
    { label: 'Online predictions', value: 'Serve predictions online from a running service.' },
    { label: 'Batch jobs', value: 'Run models as scheduled or on-demand batch jobs.' },
    { label: 'Local experiments', value: 'Experiment locally only; no production model serving planned.' },
  ],
  ai_usage: [
    { label: '1–5 short calls / month', value: 'About 1–5 short AI calls per user per month.' },
    { label: '10+ short calls / month', value: 'About 10 or more short AI calls per user per month.' },
    { label: 'Long documents / reports', value: 'About 1–5 long document or report-generation calls per user per month.' },
    { label: 'Not sure', value: "I don't know yet; please estimate conservatively." },
  ],
};

export function questionPresets(questionId: string): readonly QuestionPreset[] {
  return PRESETS[questionId] ?? [];
}
