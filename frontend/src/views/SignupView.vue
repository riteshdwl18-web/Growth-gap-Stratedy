<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { signup } from '../services/auth'

const router = useRouter()
const route = useRoute()
const brandName = 'EquityEdge'
const brandTagline = 'Insight. Strategy. Growth.'
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMessage = ref('')

const passwordMismatch = computed(
  () => confirmPassword.value.length > 0 && password.value !== confirmPassword.value,
)

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

async function submitSignup(): Promise<void> {
  errorMessage.value = ''
  if (!isValidEmail(email.value)) {
    errorMessage.value = 'Please enter a valid email address'
    return
  }
  if (passwordMismatch.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  loading.value = true
  try {
    await signup({
      email: email.value.trim(),
      password: password.value,
    })

    const redirectTo = String(route.query.redirect ?? '/dashboard')
    await router.replace(redirectTo)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Signup failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-container fluid class="signup-page pa-0">
    <div class="signup-bg"></div>
    <v-row class="signup-row ma-0" align="center" justify="center">
      <v-col cols="12" sm="11" md="10" lg="8" xl="7">
        <v-card class="signup-shell" rounded="lg" elevation="0">
          <v-row class="ma-0">
            <v-col cols="12" md="6" class="brand-pane">
              <img src="/equityedge-logo.svg" alt="EquityEdge logo" class="auth-brand-logo" />
              <div class="brand-pill">First-Time Setup</div>
              <h1 class="brand-name">{{ brandName }}</h1>
              <div class="brand-tagline">{{ brandTagline }}</div>
              <p class="brand-copy">
                Create your first account to unlock the trading dashboard,
                run workflows, and export strategy outputs.
              </p>
            </v-col>

            <v-col cols="12" md="6" class="form-pane">
              <v-card-title class="pt-8 px-8 pb-2">
                <div>
                  <div class="text-overline text-medium-emphasis">First-Time User</div>
                  <h2 class="text-h5 font-weight-bold mb-1">Create Account</h2>
                  <div class="text-body-2 text-medium-emphasis">Set your login credentials.</div>
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
                  @keyup.enter="submitSignup"
                />

                <v-text-field
                  v-model="password"
                  label="Password"
                  type="password"
                  prepend-inner-icon="mdi-lock-outline"
                  autocomplete="new-password"
                  @keyup.enter="submitSignup"
                />

                <v-text-field
                  v-model="confirmPassword"
                  label="Confirm Password"
                  type="password"
                  prepend-inner-icon="mdi-lock-check-outline"
                  autocomplete="new-password"
                  :error="passwordMismatch"
                  :error-messages="passwordMismatch ? 'Passwords do not match' : ''"
                  @keyup.enter="submitSignup"
                />

                <v-btn
                  block
                  color="primary"
                  size="large"
                  :loading="loading"
                  :disabled="!email.trim() || !password || !confirmPassword || passwordMismatch || !isValidEmail(email)"
                  @click="submitSignup"
                >
                  Create Account
                </v-btn>

                <v-btn
                  block
                  variant="text"
                  class="mt-2"
                  color="secondary"
                  prepend-icon="mdi-arrow-left"
                  to="/login"
                >
                  Back to Login
                </v-btn>
              </v-card-text>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.signup-page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

.signup-row {
  min-height: 100vh;
  padding: 24px;
}

.signup-bg {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(160deg, rgba(15, 23, 42, 0.5) 0%, rgba(17, 24, 39, 0.68) 100%),
    url('/login-market-grid.svg') center/cover no-repeat,
    #111827;
}

.signup-shell {
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

.brand-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  padding: 7px 13px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
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

@media (max-width: 959px) {
  .signup-row {
    padding: 14px;
  }

  .brand-pane {
    padding: 26px 22px;
  }

  .brand-name {
    font-size: 32px;
  }
}
</style>
