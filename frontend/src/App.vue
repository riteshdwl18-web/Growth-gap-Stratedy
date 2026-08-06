<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useRunsController } from './composables/useRunsController'
import { getAuthStatus, logout } from './services/auth'

const controller = reactive(useRunsController())
const route = useRoute()
const router = useRouter()
const authUsername = ref('')
const isAuthenticated = ref(false)

const navGroups = [
  {
    title: 'Control Center',
    items: [
      {
        label: 'Insights Hub',
        hint: 'KPIs and strategic overview',
        path: '/dashboard',
        icon: 'mdi-view-dashboard-outline',
        heroTitle: 'Consolidated Insights Across Modules',
        heroSubtitle: 'Unified dashboard area for charts, KPIs, and cross-module performance intelligence.',
      },
    ],
  },
  {
    title: 'Screening',
    items: [
      {
        label: 'Equity Screener',
        hint: 'Scan and validate candidates',
        path: '/screener',
        icon: 'mdi-file-chart-outline',
        heroTitle: 'Validate, Process, and Run The Screener',
        heroSubtitle: 'Upload CSV, validate schema, launch the run engine, and monitor processing flow.',
      },
    ],
  },
  {
    title: 'Execution',
    items: [
      {
        label: 'Trade Journal',
        hint: 'Track execution and learning',
        path: '/journal',
        icon: 'mdi-notebook-edit-outline',
        heroTitle: 'Capture Trades, Context, and Learning',
        heroSubtitle: 'Document entries, exits, SL/TP discipline, and post-trade notes for consistent performance review.',
      },
    ],
  },
]


const activePath = computed(() => route.path)
const isLoginRoute = computed(
  () =>
    route.path === '/login'
    || route.path === '/signup'
    || route.path === '/forgot-password'
    || route.path === '/reset-password',
)
const navItems = computed(() => navGroups.flatMap((group) => group.items))
const activeNavItem = computed(() => navItems.value.find((item) => isNavItemActive(item.path)) ?? null)
const heroTitle = computed(() => activeNavItem.value?.heroTitle || 'Consolidated Insights Across Modules')
const heroSubtitle = computed(
  () =>
    activeNavItem.value?.heroSubtitle ||
    'Unified dashboard area for charts, KPIs, and cross-module performance intelligence.',
)
const heroModuleLabel = computed(() => activeNavItem.value?.label || 'Insights Hub')
const userInitials = computed(() => {
  const raw = authUsername.value.trim()
  if (!raw) {
    return 'U'
  }
  const parts = raw.split(/\s+/).filter((part) => part.length > 0)
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
})

function isNavItemActive(path: string): boolean {
  if (path === '/screener' && (activePath.value === '/runs' || activePath.value.startsWith('/runs/'))) {
    return true
  }
  return activePath.value === path || activePath.value.startsWith(`${path}/`)
}

function goTo(path: string): void {
  if (route.path !== path) {
    void router.push(path)
  }
}

async function refreshAuthStatus(): Promise<void> {
  const status = await getAuthStatus()
  authUsername.value = status.username ?? ''
  isAuthenticated.value = status.authenticated
}

async function handleLogout(): Promise<void> {
  await logout()
  controller.stopPolling()
  await router.replace('/login')
}

async function ensureAppInitialized(): Promise<void> {
  if (isLoginRoute.value) {
    controller.stopPolling()
    return
  }
  if (!isAuthenticated.value) {
    controller.stopPolling()
    return
  }
  await controller.initialize()
}

onMounted(async () => {
  await refreshAuthStatus()
  await ensureAppInitialized()
})

watch(
  () => route.path,
  async () => {
    await refreshAuthStatus()
    await ensureAppInitialized()
  },
)

onUnmounted(() => {
  controller.stopPolling()
})
</script>

<template>
  <v-app class="app-shell">
    <v-main v-if="isLoginRoute">
      <RouterView />
    </v-main>

    <template v-else>
    <v-app-bar flat height="76" class="top-bar">
      <v-container fluid class="app-container d-flex align-center justify-space-between px-4">
        <div>
          <div class="brand-kicker">Nexora Markets</div>
          <div class="brand-title">Quant Workspace</div>
        </div>
        <div class="d-flex align-center ga-3">
          <v-btn
            variant="tonal"
            color="primary"
            prepend-icon="mdi-shield-lock-outline"
            size="small"
            class="security-btn"
            @click="goTo('/account/security')"
          >
            Security
          </v-btn>
          <div v-if="authUsername" class="user-profile-badge">
            <div class="user-avatar">{{ userInitials }}</div>
            <div class="user-meta">
              <div class="user-name">{{ authUsername }}</div>
              <div class="user-role">Trader</div>
            </div>
          </div>
          <v-btn
            variant="tonal"
            color="secondary"
            icon="mdi-logout"
            size="small"
            class="logout-btn"
            @click="handleLogout"
          />
        </div>
      </v-container>
    </v-app-bar>

    <v-main>
      <v-container fluid class="app-container py-8">
        <v-sheet class="hero-panel mb-5" rounded="xl">
          <div class="hero-grid">
            <div>
              <div class="text-overline mb-1">Operational Overview</div>
              <h1 class="hero-title">{{ heroTitle }}</h1>
              <p class="hero-subtitle">{{ heroSubtitle }}</p>
            </div>
            <div class="hero-meta d-none d-md-flex">
              <v-chip color="primary" variant="flat" prepend-icon="mdi-compass-outline" size="small">
                {{ heroModuleLabel }}
              </v-chip>
            </div>
          </div>
        </v-sheet>

        <v-layout class="workspace-layout">
          <v-navigation-drawer
            class="workspace-drawer d-none d-md-flex"
            permanent
            :width="286"
            rounded="xl"
          >
            <v-list class="pt-2">
              <v-list-item
                class="workspace-drawer-header"
                prepend-icon="mdi-view-grid-outline"
                title="Module Navigator"
                subtitle="Browse workspace sections"
              />
            </v-list>

            <v-divider />

            <v-list class="left-nav-list" nav density="comfortable">
              <template v-for="group in navGroups" :key="group.title">
                <v-list-subheader class="left-nav-group-title">{{ group.title }}</v-list-subheader>
                <v-list-item
                  v-for="item in group.items"
                  :key="item.path"
                  class="left-nav-item"
                  :prepend-icon="item.icon"
                  :title="item.label"
                  :subtitle="item.hint"
                  rounded="lg"
                  :active="isNavItemActive(item.path)"
                  @click="goTo(item.path)"
                />
              </template>
            </v-list>

            <div class="drawer-footer">
              <div class="drawer-footer-kicker">Workspace Mode</div>
              <div class="drawer-footer-title">Production Console</div>
              <div class="drawer-footer-copy">Structured navigation for research, screening, and execution workflows.</div>
            </div>
          </v-navigation-drawer>

          <div class="workspace-content">
            <v-sheet class="mobile-nav-strip mb-4 d-md-none" rounded="xl">
              <div class="d-flex ga-2 flex-wrap">
                <v-btn
                  v-for="item in navItems"
                  :key="item.path"
                  :prepend-icon="item.icon"
                  :variant="isNavItemActive(item.path) ? 'flat' : 'tonal'"
                  :color="isNavItemActive(item.path) ? 'primary' : 'secondary'"
                  @click="goTo(item.path)"
                >
                  {{ item.label }}
                </v-btn>
              </div>
            </v-sheet>

            <RouterView />
          </div>
        </v-layout>
      </v-container>
    </v-main>
    </template>
  </v-app>
</template>

<style scoped>
.user-profile-badge {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(20, 48, 84, 0.14);
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.96) 0%, rgba(243, 249, 255, 0.95) 100%);
  border-radius: 999px;
  padding: 6px 12px 6px 6px;
  box-shadow: 0 10px 18px rgba(20, 55, 108, 0.12);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #eef5ff;
  background: linear-gradient(145deg, #2e5aa1 0%, #1b3f77 100%);
}

.user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.user-name {
  font-size: 12px;
  font-weight: 600;
  color: #1d2f4c;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #6b7f9e;
}

.logout-btn {
  border: 1px solid rgba(20, 48, 84, 0.12);
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.96) 0%, rgba(241, 248, 255, 0.95) 100%);
}

.security-btn {
  border: 1px solid rgba(15, 76, 160, 0.24);
  background: linear-gradient(140deg, rgba(239, 247, 255, 0.95) 0%, rgba(228, 241, 255, 0.95) 100%);
  box-shadow: 0 8px 16px rgba(23, 75, 145, 0.16);
}

@media (max-width: 760px) {
  .user-profile-badge {
    padding-right: 8px;
  }

  .user-name {
    max-width: 90px;
  }
}
</style>
