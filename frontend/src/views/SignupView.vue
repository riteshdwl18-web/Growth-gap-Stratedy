<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { signup } from '../services/auth'

const router = useRouter()
const route = useRoute()
const brandName = 'Nexora Markets'
const brandTagline = 'Quant Workspace'
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMessage = ref('')

const passwordMismatch = computed(
  () => confirmPassword.value.length > 0 && password.value !== confirmPassword.value,
)

async function submitSignup(): Promise<void> {
  errorMessage.value = ''
  if (passwordMismatch.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  loading.value = true
  try {
    await signup({
      username: username.value.trim(),
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
        <v-card class="signup-shell" rounded="xl" elevation="14">
          <v-row class="ma-0">
            <v-col cols="12" md="6" class="brand-pane">
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
                  v-model="username"
                  label="Username"
                  prepend-inner-icon="mdi-account-outline"
                  autocomplete="username"
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
                  :disabled="!username.trim() || !password || !confirmPassword || passwordMismatch"
                  @click="submitSignup"
                >
                  Create Account
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
    linear-gradient(135deg, rgba(238, 243, 250, 0.28) 0%, rgba(213, 226, 243, 0.28) 100%),
    url('/login-market-grid.svg') center/cover no-repeat,
    radial-gradient(circle at 15% 20%, rgba(255, 217, 61, 0.2) 0%, transparent 34%),
    radial-gradient(circle at 80% 72%, rgba(11, 96, 176, 0.22) 0%, transparent 40%),
    linear-gradient(135deg, #eef3fa 0%, #e4edf8 42%, #d5e2f3 100%);
}

.signup-shell {
  position: relative;
  border: 1px solid rgba(31, 47, 70, 0.12);
  overflow: hidden;
}

.brand-pane {
  background:
    linear-gradient(155deg, rgba(9, 37, 78, 0.94) 0%, rgba(12, 59, 122, 0.92) 52%, rgba(16, 75, 155, 0.9) 100%);
  color: #f2f7ff;
  padding: 42px 36px;
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
  background: rgba(255, 255, 255, 0.97);
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
