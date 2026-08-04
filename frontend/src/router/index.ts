import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import RunDetailsView from '../views/RunDetailsView.vue'
import RunsView from '../views/RunsView.vue'
import SignupView from '../views/SignupView.vue'
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
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: true },
    },
    {
      path: '/runs',
      name: 'runs',
      component: RunsView,
      meta: { requiresAuth: true },
    },
    {
      path: '/runs/:runId',
      name: 'run-details',
      component: RunDetailsView,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const authStatus = await getAuthStatus()

  if (authStatus.signup_required && to.path !== '/signup') {
    return {
      path: '/signup',
      query: { redirect: to.fullPath },
    }
  }

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
