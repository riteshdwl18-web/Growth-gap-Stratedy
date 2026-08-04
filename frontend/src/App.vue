<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useRunsController } from './composables/useRunsController'
import { getAuthStatus, logout } from './services/auth'

const controller = reactive(useRunsController())
const route = useRoute()
const router = useRouter()
const authUsername = ref('')

const navItems = [
  { label: 'Dashboard', path: '/dashboard' },
  { label: 'Runs & Results', path: '/runs' },
]

const workflowStages = [
  { id: 1, label: 'Dashboard', hint: 'Validate CSV and start a run' },
  { id: 2, label: 'Runs', hint: 'Monitor status and control active runs' },
  { id: 3, label: 'Results', hint: 'Inspect output and export data' },
]

const activePath = computed(() => route.path)
const isLoginRoute = computed(() => route.path === '/login' || route.path === '/signup')
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
const activeStage = computed(() => {
  if (route.path.startsWith('/runs/')) {
    return 3
  }
  if (route.path.startsWith('/runs')) {
    return 2
  }
  return 1
})

function goTo(path: string): void {
  if (route.path !== path) {
    void router.push(path)
  }
}

async function refreshAuthStatus(): Promise<void> {
  const status = await getAuthStatus()
  authUsername.value = status.username ?? ''
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
              <h1 class="hero-title">Screen, Track, and Export With Confidence</h1>
              <p class="hero-subtitle">
                Production workflow for strict CSV validation, async orchestration, progress visibility, and downloadable outputs.
              </p>
            </div>
          </div>
        </v-sheet>

        <v-sheet class="nav-strip mb-5" rounded="xl">
          <div class="d-flex ga-2 flex-wrap">
            <v-btn
              v-for="item in navItems"
              :key="item.path"
              :variant="activePath === item.path ? 'flat' : 'tonal'"
              :color="activePath === item.path ? 'primary' : 'secondary'"
              @click="goTo(item.path)"
            >
              {{ item.label }}
            </v-btn>
          </div>
        </v-sheet>

        <v-sheet class="workflow-rail mb-5" rounded="xl">
          <div class="workflow-rail-grid">
            <div
              v-for="stage in workflowStages"
              :key="stage.id"
              class="workflow-node"
              :class="{ 'is-active': activeStage === stage.id, 'is-complete': activeStage > stage.id }"
            >
              <div class="workflow-dot">{{ stage.id }}</div>
              <div>
                <div class="workflow-label">{{ stage.label }}</div>
                <div class="workflow-hint">{{ stage.hint }}</div>
              </div>
            </div>
          </div>
        </v-sheet>

        <RouterView />
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
  border: 1px solid rgba(20, 48, 84, 0.12);
  background: rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  padding: 6px 12px 6px 6px;
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
