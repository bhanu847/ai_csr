import { Routes } from '@angular/router';

import { AgentDetailComponent } from './agent-detail.component';
import { AgentListComponent } from './agent-list.component';
import { AnalyticsComponent } from './analytics.component';
import { authGuard } from './auth.guard';
import { CallsViewComponent } from './calls-view.component';
import { CustomerListComponent } from './customer-list.component';
import { DashboardComponent } from './dashboard.component';
import { LoginComponent } from './login.component';
import { RegisterComponent } from './register.component';
import { SupervisorDashboardComponent } from './supervisor-dashboard.component';
import { TrainingCenterComponent } from './training-center.component';
import { WorkflowDetailComponent } from './workflow-detail.component';
import { WorkflowListComponent } from './workflow-list.component';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'agents', component: AgentListComponent, canActivate: [authGuard] },
  { path: 'agents/:id', component: AgentDetailComponent, canActivate: [authGuard] },
  { path: 'calls', component: CallsViewComponent, canActivate: [authGuard] },
  { path: 'customers', component: CustomerListComponent, canActivate: [authGuard] },
  { path: 'analytics', component: AnalyticsComponent, canActivate: [authGuard] },
  { path: 'training', component: TrainingCenterComponent, canActivate: [authGuard] },
  { path: 'workflows', component: WorkflowListComponent, canActivate: [authGuard] },
  { path: 'workflows/:id', component: WorkflowDetailComponent, canActivate: [authGuard] },
  { path: 'live', component: SupervisorDashboardComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: 'dashboard' },
];
