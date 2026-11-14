import { questionPresets } from './question-presets';
import { normalizeQuestion } from '../models';

describe('questionPresets', () => {
  it('provides practical budget and traffic shortcuts', () => {
    expect(questionPresets('budget').map((preset) => preset.label)).toContain('€100 / month');
    expect(questionPresets('traffic_start').map((preset) => preset.value)).toContain('About 50,000 requests per day');
  });

  it('includes the backend example as an editable database suggestion', () => {
    expect(questionPresets('database').some((preset) =>
      preset.value.includes('PostgreSQL, managed by a cloud provider') && preset.value.includes('60 GB in 12 months'),
    )).toBe(true);
  });

  it('covers common infrastructure questions that otherwise require free-form typing', () => {
    for (const id of ['where_running', 'existing_infra_notes', 'which_service', 'managed_backend', 'paas', 'model_usage']) {
      expect(questionPresets(id).length).toBeGreaterThan(0);
    }
    expect(questionPresets('where_running').map((preset) => preset.label)).toContain('AWS');
    expect(questionPresets('which_service').map((preset) => preset.label)).toContain('All services');
  });

  it('normalizes backend text questions that omit kind so their presets are available', () => {
    for (const id of ['managed_backend', 'deploy_frequency', 'ai_usage']) {
      const question = normalizeQuestion({ id, question: 'Backend question without a kind field' });
      expect(question.kind).toBe('text');
      expect(questionPresets(question.id).length).toBeGreaterThan(0);
    }
  });

  it('returns no suggestions for questions without useful presets', () => {
    expect(questionPresets('unknown-question')).toEqual([]);
  });

  it('keeps every suggested answer editable and non-empty', () => {
    for (const id of [
      'budget', 'traffic_start', 'database', 'region', 'deploy_frequency', 'focus', 'real_traffic',
      'where_running', 'existing_infra_notes', 'which_service', 'managed_backend', 'paas', 'model_usage',
      'spikes', 'current_cost', 'environments', 'deployment_status', 'payment_compliance', 'ml_serving', 'ai_usage',
    ]) {
      for (const preset of questionPresets(id)) {
        expect(preset.label.trim().length).toBeGreaterThan(0);
        expect(preset.value.trim().length).toBeGreaterThan(0);
      }
    }
  });
});
