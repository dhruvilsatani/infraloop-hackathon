import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ProfileDrawerComponent } from './components/profile-drawer/profile-drawer';
import { SiteHeaderComponent } from './components/site-header/site-header';
import { ProfileService } from './core/profile.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, SiteHeaderComponent, ProfileDrawerComponent],
  templateUrl: './app.html',
})
export class App {
  protected readonly profile = inject(ProfileService);
}
