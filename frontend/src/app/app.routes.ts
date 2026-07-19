import { Routes } from '@angular/router';

import { AgentDetailComponent } from './agent-detail.component';
import { AgentListComponent } from './agent-list.component';
import { authGuard } from './auth.guard';
import { CallsViewComponent } from './calls-view.component';
import { LoginComponent } from './login.component';
import { RegisterComponent } from './register.component';

export const routes: Routes = [
  { path: '', redirectTo: 'agents', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  { path: 'agents', component: AgentListComponent, canActivate: [authGuard] },
  { path: 'agents/:id', component: AgentDetailComponent, canActivate: [authGuard] },
  { path: 'calls', component: CallsViewComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: 'agents' },
];
