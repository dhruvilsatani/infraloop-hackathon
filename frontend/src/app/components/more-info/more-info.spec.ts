import { TestBed } from '@angular/core/testing';
import { MoreInfoComponent } from './more-info';

describe('MoreInfoComponent', () => {
  it('toggles the panel and updates its accessible expanded state', async () => {
    await TestBed.configureTestingModule({ imports: [MoreInfoComponent] }).compileComponents();
    const fixture = TestBed.createComponent(MoreInfoComponent);
    fixture.componentRef.setInput('title', 'Recommendation details');
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.more-info-toggle') as HTMLButtonElement;
    const panel = fixture.nativeElement.querySelector('.more-info-panel') as HTMLElement;
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(panel.hasAttribute('inert')).toBe(true);

    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(panel.classList.contains('expanded')).toBe(true);
    expect(panel.hasAttribute('inert')).toBe(false);

    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(panel.classList.contains('expanded')).toBe(false);
    expect(panel.hasAttribute('inert')).toBe(true);
  });
});
