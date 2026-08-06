import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import LoginView from '../views/LoginView.vue'
import ForgotPasswordView from '../views/ForgotPasswordView.vue'
import ResetPasswordView from '../views/ResetPasswordView.vue'
import RunDetailsView from '../views/RunDetailsView.vue'
import ScreenerView from '../views/ScreenerView.vue'
import SignupView from '../views/SignupView.vue'
import TradingJournalView from '../views/TradingJournalView.vue'
import { getAuthStatus } from '../services/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login',
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/signup',
      name: 'signup',
      component: SignupView,
      meta: { public: true },
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: ForgotPasswordView,
      meta: { public: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: ResetPasswordView,
      meta: { public: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: true },
    },
    {
      path: '/screener',
      name: 'screener',
      component: ScreenerView,
      meta: { requiresAuth: true },
    },
    {
      path: '/runs',
      name: 'runs',
      redirect: '/screener',
    },
    {
      path: '/runs/:runId',
      name: 'run-details',
      component: RunDetailsView,
      meta: { requiresAuth: true },
    },
    {
      path: '/journal',
      name: 'trading-journal',
      component: TradingJournalView,
      meta: { requiresAuth: true },
    },
    {
      path: '/account/security',
      name: 'account-security',
      component: ChangePasswordView,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const authStatus = await getAuthStatus()

  if (to.meta.requiresAuth && !authStatus.authenticated) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  if ((to.path === '/login' || to.path === '/signup') && authStatus.authenticated) {
    return '/dashboard'
  }

  return true
})

export default router
