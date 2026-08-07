<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { login } from '../services/auth'

const router = useRouter()
const route = useRoute()
const brandName = 'EquityEdge'
const brandTagline = 'Insight. Strategy. Growth.'
const email = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

async function submitLogin(): Promise<void> {
  errorMessage.value = ''
  if (!isValidEmail(email.value)) {
    errorMessage.value = 'Please enter a valid email address'
    return
  }
  loading.value = true
  try {
    await login({
      email: email.value.trim(),
      password: password.value,
    })
    const redirectTo = String(route.query.redirect ?? '/dashboard')
    await router.replace(redirectTo)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Login failed'
  } finally {
    loading.value = false
  }
}

</script>

<template>
  <v-container fluid class="login-page pa-0">
    <div class="login-bg"></div>
    <v-row class="login-row ma-0" align="center" justify="center">
      <v-col cols="12" sm="11" md="10" lg="8" xl="7">
        <v-card class="login-shell" rounded="lg" elevation="0">
          <v-row class="ma-0">
            <v-col cols="12" md="6" class="brand-pane">
              <img src="/equityedge-logo.svg" alt="EquityEdge logo" class="auth-brand-logo" />
              <h1 class="brand-name">{{ brandName }}</h1>
              <div class="brand-tagline">{{ brandTagline }}</div>
              <p class="brand-copy">
                Centralized environment for screening, execution readiness checks,
                and evidence-backed review of high-conviction symbols.
              </p>

              <div class="stat-grid">
                <div class="stat-card">
                  <div class="stat-label">Universe Scan</div>
                  <div class="stat-value">500+</div>
                </div>
                <div class="stat-card">
                  <div class="stat-label">Signal Refresh</div>
                  <div class="stat-value">Real-Time</div>
                </div>
                <div class="stat-card">
                  <div class="stat-label">Risk Snapshot</div>
                  <div class="stat-value">Portfolio-Ready</div>
                </div>
                <div class="stat-card">
                  <div class="stat-label">Export</div>
                  <div class="stat-value">One Click</div>
                </div>
              </div>
            </v-col>

            <v-col cols="12" md="6" class="form-pane">
              <v-card-title class="pt-8 px-8 pb-2">
                <div>
                  <div class="text-overline text-medium-emphasis">Secure Access</div>
                  <h2 class="text-h5 font-weight-bold mb-1">Sign In</h2>
                  <div class="text-body-2 text-medium-emphasis">Login is required to access dashboard and runs.</div>
                </div>
              </v-card-title>

              <v-card-text class="px-8 pb-8">
                <v-alert
                  v-if="errorMessage"
                  type="error"
                  variant="tonal"
                  density="comfortable"
                  class="mb-4"
                  closable
                  @click:close="errorMessage = ''"
                >
                  {{ errorMessage }}
                </v-alert>

                <v-text-field
                  v-model="email"
                  label="Email"
                  type="email"
                  prepend-inner-icon="mdi-email-outline"
                  autocomplete="email"
                  @keyup.enter="submitLogin"
                />

                <v-text-field
                  v-model="password"
                  label="Password"
                  type="password"
                  prepend-inner-icon="mdi-lock-outline"
                  autocomplete="current-password"
                  @keyup.enter="submitLogin"
                />

                <v-btn
                  block
                  color="primary"
                  size="large"
                  :loading="loading"
                  :disabled="!email.trim() || !password || !isValidEmail(email)"
                  @click="submitLogin"
                >
                  Login
                </v-btn>

                <div class="text-body-2 text-medium-emphasis text-center mt-3">
                  <router-link class="signup-link" to="/forgot-password">Forgot password?</router-link>
                </div>

                <div class="text-body-2 text-medium-emphasis text-center mt-4">
                  First time user?
                  <router-link class="signup-link" to="/signup">Create account</router-link>
                </div>
              </v-card-text>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

.login-row {
  min-height: 100vh;
  padding: 24px;
}

.login-bg {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(160deg, rgba(15, 23, 42, 0.5) 0%, rgba(17, 24, 39, 0.68) 100%),
    url('/login-market-grid.svg') center/cover no-repeat,
    #111827;
}

.login-shell {
  position: relative;
  border: 1px solid #e2e5ea;
  overflow: hidden;
}

.brand-pane {
  background: #1d2939;
  color: #f2f7ff;
  padding: 42px 36px;
}

.auth-brand-logo {
  width: 124px;
  max-width: 100%;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.1);
  padding: 8px;
}

.brand-name {
  margin-top: 18px;
  font-size: 42px;
  line-height: 1.06;
  letter-spacing: 0.01em;
}

.brand-tagline {
  margin-top: 8px;
  font-size: 20px;
  color: rgba(242, 247, 255, 0.86);
}

.brand-copy {
  margin-top: 16px;
  margin-bottom: 22px;
  font-size: 15px;
  line-height: 1.5;
  color: rgba(242, 247, 255, 0.8);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.stat-card {
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.08);
}

.stat-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(242, 247, 255, 0.72);
}

.stat-value {
  margin-top: 4px;
  font-weight: 600;
  font-size: 15px;
}

.form-pane {
  background: #ffffff;
}

.form-pane :deep(.v-card-title) {
  padding-top: 42px !important;
}

.form-pane :deep(.v-field__input) {
  min-height: 48px;
}

.form-pane :deep(.v-btn) {
  letter-spacing: 0.06em;
}

.signup-link {
  color: #2563eb;
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.signup-link:hover {
  text-decoration: underline;
}

@media (max-width: 959px) {
  .login-row {
    padding: 14px;
  }

  .brand-pane {
    padding: 26px 22px;
  }

  .brand-name {
    font-size: 32px;
  }

  .stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
