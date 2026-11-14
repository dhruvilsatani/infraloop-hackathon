import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ConfigureStepComponent } from '../components/configure-step/configure-step';
import { FilesStepComponent } from '../components/files-step/files-step';
import { PreviewResponse, Target } from '../models';
import { WizardService } from './wizard.service';

const target: Target = {
  id: 'test-target',
  label: 'Test platform',
  provider: 'Test',
  monthly_eur: 12,
  zone_ha: false,
  recommended: true,
  files: true,
  note: 'Test option',
  profile: 'test',
  catch: '',
  drawbacks: [],
  benefits: [],
  links: [],
  short: 'Test platform',
  why: [],
  brief: '',
};

const preview: PreviewResponse = {
  docs: [{ path: 'MANIFEST.md', title: 'Manifest', content: '# Manifest' }],
  files: [{ path: 'Dockerfile', title: 'Dockerfile', content: 'FROM scratch', group: 'basic' }],
  advice: [],
  skipped: [],
};

describe('async page loading placeholders', () => {
  it('shows the configure skeleton, then replaces it with target options', async () => {
    const targets = signal<Target[]>([]);
    const selectedTargetId = signal(target.id);
    const selectedTarget = computed(() => targets().find((item) => item.id === selectedTargetId()) ?? null);
    const recommendedTarget = computed(() => targets().find((item) => item.recommended) ?? null);
    let finishLoad!: () => void;
    const wizard = {
      targets,
      selectedTargetId,
      selectedTarget,
      recommendedTarget,
      gaps: signal([]),
      budget: signal<number | null>(null),
      aiWritten: signal(false),
      loadTargets: () =>
        new Promise<void>((resolve) => {
          finishLoad = () => {
            targets.set([target]);
            resolve();
          };
        }),
    };

    await TestBed.configureTestingModule({
      imports: [ConfigureStepComponent],
      providers: [provideRouter([]), { provide: WizardService, useValue: wizard }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ConfigureStepComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.option-skeleton').length).toBe(8);
    expect(fixture.nativeElement.querySelector('.configure-skeleton')?.getAttribute('role')).toBe('status');

    finishLoad();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.configure-skeleton')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.option').length).toBe(1);
  });

  it('shows the files skeleton, then replaces it with the preview tree', async () => {
    const previewState = signal<PreviewResponse | null>(null);
    let finishLoad!: () => void;
    const wizard = {
      preview: previewState,
      selectedTargetId: signal(target.id),
      loadPreview: () =>
        new Promise<PreviewResponse>((resolve) => {
          finishLoad = () => {
            previewState.set(preview);
            resolve(preview);
          };
        }),
    };

    await TestBed.configureTestingModule({
      imports: [FilesStepComponent],
      providers: [provideRouter([]), { provide: WizardService, useValue: wizard }],
    }).compileComponents();

    const fixture = TestBed.createComponent(FilesStepComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.files-skeleton')?.getAttribute('role')).toBe('status');
    expect(fixture.nativeElement.querySelectorAll('.skeleton-tree-row').length).toBe(10);

    finishLoad();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.files-skeleton')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.tree-row').length).toBe(2);
  });
});
