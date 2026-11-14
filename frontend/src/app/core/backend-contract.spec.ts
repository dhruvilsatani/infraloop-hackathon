import targetsFixture from '../mock/fixtures/targets.json';
import previewFixture from '../mock/fixtures/preview.json';
import previewHetznerFixture from '../mock/fixtures/preview-hetzner.json';
import { PreviewResponse, TargetsResponse } from '../models';

// These fixtures are real responses captured from the backend (see mock/fixtures).
// If the backend changes its shape, these tests fail and show what moved.
const targets = targetsFixture as TargetsResponse;
const basic = previewFixture as PreviewResponse;
const withHetzner = previewHetznerFixture as PreviewResponse;

describe('backend contract: /targets', () => {
  it('has exactly one recommended option, and it is priced', () => {
    const recommended = targets.targets.filter((t) => t.recommended);
    expect(recommended.length).toBe(1);
    expect(recommended[0].monthly_eur).not.toBeNull();
  });

  it('leaves the price empty for options that are not priced', () => {
    const unpriced = targets.targets.filter((t) => t.monthly_eur === null).map((t) => t.id);
    expect(unpriced).toEqual(expect.arrayContaining(['other-cloud', 'not-yet']));
  });

  it('gives every option a plain-language note and a list of drawbacks', () => {
    for (const t of targets.targets) {
      expect(t.short.length).toBeGreaterThan(0);
      expect(Array.isArray(t.drawbacks)).toBe(true);
    }
  });
});

describe('backend contract: /preview', () => {
  it('returns guides and basic files without a target', () => {
    expect(basic.docs.map((d) => d.path)).toEqual(expect.arrayContaining(['IMPLEMENTATION.md', 'MANIFEST.md']));
    expect(basic.files.every((f) => f.group === 'basic')).toBe(true);
  });

  it('adds the chosen setup\'s files, marked as cloud', () => {
    const cloud = withHetzner.files.filter((f) => f.group === 'cloud').map((f) => f.path);
    expect(cloud).toEqual(expect.arrayContaining(['infra/hetzner/main.tf', 'docker-compose.prod.yml']));
    expect(withHetzner.files.length).toBeGreaterThan(basic.files.length);
  });

  it('returns advice titles and skip reasons, the parts the report shows', () => {
    expect(basic.advice.length).toBeGreaterThan(0);
    expect(basic.advice[0].title.length).toBeGreaterThan(0);
    expect(basic.skipped.every((s) => s.reason.length > 0)).toBe(true);
  });
});
