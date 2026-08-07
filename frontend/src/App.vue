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

type NavItem = {
  label: string
  hint: string
  path: string
  icon: string
  heroTitle?: string
  heroSubtitle?: string
  badge?: string
  disabled?: boolean
}

type NavGroup = {
  title: string
  icon: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    title: 'Workspace',
    icon: 'mdi-view-grid-outline',
    items: [
      {
        label: 'Dashboard',
        hint: 'Metrics and overview',
        path: '/dashboard',
        icon: 'mdi-view-dashboard-outline',
        heroTitle: 'Consolidated Insights Across Modules',
        heroSubtitle: 'Unified dashboard area for charts, KPIs, and cross-module performance intelligence.',
      },
      {
        label: 'Journal',
        hint: 'Execution notes and review',
        path: '/journal',
        icon: 'mdi-notebook-edit-outline',
        heroTitle: 'Capture Trades, Context, and Learning',
        heroSubtitle: 'Document entries, exits, SL/TP discipline, and post-trade notes for consistent performance review.',
      },
      {
        label: 'Account',
        hint: 'Security and profile settings',
        path: '/account/security',
        icon: 'mdi-account-cog-outline',
        heroTitle: 'Account Security and Session Controls',
        heroSubtitle: 'Manage account access, passwords, and security preferences from one place.',
      },
    ],
  },
  {
    title: 'Intelligence',
    icon: 'mdi-radar',
    items: [
      {
        label: 'Equity Screener',
        hint: 'Scan and validate candidates',
        path: '/screener',
        icon: 'mdi-file-chart-outline',
        heroTitle: 'Validate, Process, and Run The Screener',
        heroSubtitle: 'Upload CSV, validate schema, launch the run engine, and monitor processing flow.',
        badge: 'Core',
      },
      {
        label: 'Wave AI',
        hint: 'Insights assistant',
        path: '',
        icon: 'mdi-brain',
        disabled: true,
        badge: 'Pro',
      },
    ],
  },
  {
    title: 'Markets',
    icon: 'mdi-finance',
    items: [
      {
        label: 'Charts',
        hint: 'Visual market study',
        path: '',
        icon: 'mdi-chart-line',
        disabled: true,
      },
      {
        label: 'Crypto',
        hint: 'Digital assets workspace',
        path: '',
        icon: 'mdi-currency-btc',
        disabled: true,
      },
    ],
  },
  {
    title: 'Tools',
    icon: 'mdi-toolbox-outline',
    items: [
      {
        label: 'Backtest',
        hint: 'Strategy validation tools',
        path: '',
        icon: 'mdi-chart-box-outline',
        disabled: true,
        badge: 'Pro',
      },
      {
        label: 'Calculators',
        hint: 'Risk and position sizing',
        path: '',
        icon: 'mdi-calculator-variant-outline',
        disabled: true,
      },
      {
        label: 'Alerts',
        hint: 'Signal and trigger rules',
        path: '',
        icon: 'mdi-bell-ring-outline',
        disabled: true,
      },
    ],
  },
]


function groupForActivePath(): NavGroup {
  return (
    navGroups.find((group) => group.items.some((item) => isNavItemActive(item.path)))
    ?? navGroups[0]
  )
}

const activeGroupTitle = ref(navGroups[0].title)
const activeGroup = computed(
  () => navGroups.find((group) => group.title === activeGroupTitle.value) ?? navGroups[0],
)

function selectGroup(title: string): void {
  activeGroupTitle.value = title
}

const activePath = computed(() => route.path)
const isLoginRoute = computed(
  () =>
    route.path === '/login'
    || route.path === '/signup'
    || route.path === '/forgot-password'
    || route.path === '/reset-password',
)
const navItems = computed<NavItem[]>(() => navGroups.flatMap((group) => group.items))
const quickNavItems = computed(() => navItems.value.filter((item) => !item.disabled && item.path).slice(0, 4))
const activeNavItem = computed(() => navItems.value.find((item) => isNavItemActive(item.path)) ?? null)
const heroTitle = computed(() => activeNavItem.value?.heroTitle || 'Consolidated Insights Across Modules')
const heroSubtitle = computed(
  () =>
    activeNavItem.value?.heroSubtitle ||
    'Unified dashboard area for charts, KPIs, and cross-module performance intelligence.',
)
const heroModuleLabel = computed(() => activeNavItem.value?.label || 'Insights Hub')
const currentYear = computed(() => new Date().getFullYear())
const apiStatusColor = computed(() => {
  if (controller.healthStatus === 'online') {
    return 'success'
  }
  if (controller.healthStatus === 'checking') {
    return 'warning'
  }
  return 'error'
})
const apiStatusLabel = computed(() => {
  if (controller.healthStatus === 'online') {
    return 'API Live'
  }
  if (controller.healthStatus === 'checking') {
    return 'API Checking'
  }
  return 'API Offline'
})
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
  if (!path) {
    return false
  }
  if (path === '/screener' && (activePath.value === '/runs' || activePath.value.startsWith('/runs/'))) {
    return true
  }
  return activePath.value === path || activePath.value.startsWith(`${path}/`)
}

function canOpenNavItem(item: { disabled?: boolean; path?: string }): boolean {
  return !item.disabled && !!item.path
}

function goTo(path: string): void {
  if (!path) {
    return
  }
  if (route.path !== path) {
    void router.push(path)
  }
}

async function refreshAuthStatus(): Promise<void> {
  const status = await getAuthStatus()
  authUsername.value = status.email ?? status.username ?? ''
  isAuthenticated.value = status.authenticated
}

async function handleLogout(): Promise<void> {
  await logout()
  controller.stopPolling()
  await router.replace('/login')
}

function isRunsRelevantRoute(path: string): boolean {
  return path === '/screener' || path === '/runs' || path.startsWith('/runs/')
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
  if (isRunsRelevantRoute(activePath.value)) {
    controller.startPolling()
  } else {
    controller.stopPolling()
  }
}

onMounted(async () => {
  activeGroupTitle.value = groupForActivePath().title
  await refreshAuthStatus()
  await ensureAppInitialized()
})

watch(
  () => route.path,
  async () => {
    activeGroupTitle.value = groupForActivePath().title
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
    <v-app-bar flat height="74" class="top-bar">
      <v-container fluid class="app-container nav-shell px-4">
        <div class="app-brand-block nav-zone-brand">
          <img src="/equityedge-logo.svg" alt="EquityEdge logo" class="app-brand-logo" />
          <div class="nav-brand-copy">
            <div class="brand-kicker">EquityEdge</div>
            <div class="brand-title">Trading Workspace</div>
            <div class="brand-subtitle">Data. Decisions. Discipline.</div>
          </div>
        </div>

        <div class="nav-zone-actions">
          <v-btn size="small" variant="flat" color="primary" class="promo-btn" prepend-icon="mdi-rocket-launch-outline">
            Go Pro
          </v-btn>
          <v-btn icon="mdi-bell-outline" size="small" variant="text" color="secondary" class="utility-icon-btn" />
          <v-btn icon="mdi-help-circle-outline" size="small" variant="text" color="secondary" class="utility-icon-btn d-none d-sm-inline-flex" />
          <v-btn
            variant="tonal"
            color="primary"
            prepend-icon="mdi-shield-lock-outline"
            size="small"
            class="security-btn"
            @click="goTo('/account/security')"
          >
            Account
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
        <v-sheet class="hero-panel mb-5" rounded="lg">
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
            :width="324"
            rounded="lg"
          >
            <div class="nav-shell-row">
              <div class="nav-rail">
                <button
                  v-for="group in navGroups"
                  :key="group.title"
                  type="button"
                  class="nav-rail-item"
                  :class="{ 'is-active': group.title === activeGroup.title }"
                  @click="selectGroup(group.title)"
                >
                  <v-icon size="20">{{ group.icon }}</v-icon>
                  <span class="nav-rail-label">{{ group.title }}</span>
                </button>
              </div>

              <div class="nav-panel">
                <div class="nav-panel-header">{{ activeGroup.title }}</div>
                <v-list class="left-nav-list" nav density="comfortable">
                  <v-list-item
                    v-for="item in activeGroup.items"
                    :key="`${activeGroup.title}-${item.label}`"
                    class="left-nav-item"
                    :class="{ 'left-nav-item-disabled': item.disabled }"
                    :prepend-icon="item.icon"
                    :title="item.label"
                    rounded="lg"
                    :active="isNavItemActive(item.path)"
                    :disabled="!canOpenNavItem(item)"
                    @click="goTo(item.path)"
                  >
                    <template #append>
                      <v-chip
                        v-if="item.badge"
                        size="x-small"
                        :color="item.badge === 'Pro' ? 'secondary' : 'primary'"
                        variant="tonal"
                        class="left-nav-badge"
                      >
                        {{ item.badge }}
                      </v-chip>
                    </template>
                  </v-list-item>
                </v-list>
              </div>
            </div>

            <div class="drawer-footer">
              <div class="drawer-footer-kicker">Workspace Mode</div>
              <div class="drawer-footer-title">Production Console</div>
              <div class="drawer-footer-copy">Structured navigation for research, screening, and execution workflows.</div>
            </div>
          </v-navigation-drawer>

          <div class="workspace-content">
            <v-sheet class="mobile-nav-strip mb-4 d-md-none" rounded="lg">
              <div class="d-flex ga-2 flex-wrap">
                <v-btn
                  v-for="item in quickNavItems"
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

    <v-footer class="app-footer" height="auto">
      <v-container fluid class="app-container">
        <v-sheet class="app-footer-panel" rounded="lg">
          <div class="app-footer-grid">
            <div class="app-footer-brand">
              <div class="app-footer-kicker">Workspace</div>
              <div class="app-footer-title">A clean and consistent trading command center.</div>
              <p class="app-footer-copy">
                A focused interface for screening runs, reviewing outcomes, and journaling execution decisions.
              </p>
              <div class="app-footer-meta" role="list">
                <div class="app-footer-meta-item" role="listitem">
                  <v-icon size="18" color="primary">mdi-compass-outline</v-icon>
                  <span>{{ heroModuleLabel }}</span>
                </div>
                <div class="app-footer-meta-item" role="listitem">
                  <v-icon size="18" :color="apiStatusColor">mdi-connection</v-icon>
                  <span>{{ apiStatusLabel }}</span>
                </div>
              </div>
            </div>

            <div class="app-footer-contact">
              <div class="app-footer-nav-title">Contact</div>
              <p class="app-footer-contact-copy">
                Growth Gap Strategy platform support and communication channels.
              </p>
              <div class="app-footer-contact-list">
                <div class="app-footer-contact-item">
                  <v-icon size="18" color="primary">mdi-phone-outline</v-icon>
                  <a href="tel:+917986277087" class="footer-contact-link">+91 7986277087</a>
                </div>
                <div class="app-footer-contact-item">
                  <v-icon size="18" color="primary">mdi-email-outline</v-icon>
                  <a href="mailto:riteshdwl18@gmail.com" class="footer-contact-link">riteshdwl18@gmail.com</a>
                </div>
              </div>
            </div>
          </div>

          <v-divider class="app-footer-divider" />

          <div class="app-footer-bottom">
            <span>© {{ currentYear }} EquityEdge. All rights reserved.</span>
            <span>Built for disciplined growth strategy workflows.</span>
          </div>
        </v-sheet>
      </v-container>
    </v-footer>
    </template>
  </v-app>
</template>

<style scoped>
.app-brand-block {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.nav-shell {
  display: grid;
  grid-template-columns: minmax(260px, auto) 1fr;
  align-items: center;
  gap: 12px;
}

.nav-zone-brand {
  min-width: 0;
}

.nav-brand-copy {
  min-width: 0;
}

.brand-subtitle {
  font-size: 0.69rem;
  color: rgb(255 255 255 / 50%);
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 250px;
}

.top-nav-pill {
  border-radius: 8px;
  min-height: 34px;
  padding-inline: 14px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: rgb(255 255 255 / 6%);
}

.nav-zone-actions {
  display: inline-flex;
  align-items: center;
  justify-self: end;
  gap: 6px;
}

.nav-module-chip {
  margin-left: 2px;
}

.promo-btn {
  border-radius: 8px;
}

.utility-icon-btn {
  border-radius: 8px;
  color: rgb(255 255 255 / 70%) !important;
}

.app-brand-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid rgb(255 255 255 / 16%);
  background: #ffffff;
  object-fit: contain;
}

.user-profile-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgb(255 255 255 / 16%);
  background: rgb(255 255 255 / 6%);
  border-radius: 999px;
  padding: 6px 12px 6px 6px;
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #ffffff;
  background: var(--accent);
}

.user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.user-name {
  font-size: 12px;
  font-weight: 600;
  color: #ffffff;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgb(255 255 255 / 50%);
}

.logout-btn {
  border: 1px solid rgb(255 255 255 / 16%);
  background: rgb(255 255 255 / 6%) !important;
  color: rgb(255 255 255 / 85%) !important;
}

.security-btn {
  border: 1px solid rgb(37 99 235 / 45%);
  background: rgb(37 99 235 / 16%) !important;
  color: #7fa8f5 !important;
}

.app-footer {
  padding: 8px 0 24px;
  background: transparent;
}

.app-footer-panel {
  border: 1px solid rgb(255 255 255 / 8%);
  background: var(--surface-dark) !important;
  padding: clamp(16px, 2vw, 22px);
}

.app-footer-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1.15fr) minmax(230px, 1fr);
  gap: 22px;
}

.app-footer-kicker {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.11em;
  color: rgb(255 255 255 / 50%);
  font-weight: 800;
}

.app-footer-title {
  margin-top: 5px;
  font-family: Manrope, sans-serif;
  font-size: clamp(1rem, 1.7vw, 1.16rem);
  font-weight: 800;
  letter-spacing: 0.01em;
  color: #ffffff;
}

.app-footer-copy {
  margin-top: 10px;
  margin-bottom: 0;
  max-width: 58ch;
  font-size: 0.86rem;
  line-height: 1.5;
  color: rgb(255 255 255 / 62%);
}

.app-footer-meta {
  margin-top: 14px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.app-footer-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgb(255 255 255 / 12%);
  background: rgb(255 255 255 / 6%);
  color: rgb(255 255 255 / 85%);
  font-size: 0.8rem;
  font-weight: 600;
}

.app-footer-nav-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgb(255 255 255 / 50%);
  font-weight: 800;
  margin-bottom: 8px;
}

.app-footer-contact-copy {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.45;
  color: rgb(255 255 255 / 62%);
}

.app-footer-contact-list {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.app-footer-contact-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgb(255 255 255 / 12%);
  background: rgb(255 255 255 / 6%);
  color: rgb(255 255 255 / 85%);
  font-size: 0.82rem;
  font-weight: 600;
}

.footer-contact-link {
  color: inherit;
  text-decoration: none;
}

.footer-contact-link:hover {
  text-decoration: underline;
}

.app-footer-divider {
  margin: 14px 0 10px;
  border-color: rgb(255 255 255 / 10%);
}

.app-footer-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 0.74rem;
  letter-spacing: 0.02em;
  color: rgb(255 255 255 / 50%);
}

@media (max-width: 760px) {
  .nav-shell {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .brand-subtitle {
    display: none;
  }

  .nav-module-chip {
    display: none !important;
  }

  .security-btn {
    min-width: 0;
    padding-inline: 10px;
  }

  .security-btn :deep(.v-btn__content) {
    font-size: 0;
  }

  .security-btn :deep(.v-icon) {
    margin-right: 0 !important;
  }

  .promo-btn {
    display: none;
  }

  .utility-icon-btn {
    display: none;
  }

  .user-profile-badge {
    padding-right: 8px;
  }

  .user-name {
    max-width: 90px;
  }

  .app-footer {
    padding-bottom: 16px;
  }

  .app-footer-grid {
    grid-template-columns: 1fr;
  }

  .app-footer-bottom {
    font-size: 0.7rem;
  }

}
</style>
