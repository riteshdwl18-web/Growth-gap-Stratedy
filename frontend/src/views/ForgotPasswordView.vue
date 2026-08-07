<script setup lang="ts">
import { ref } from 'vue'

import { forgotPassword } from '../services/auth'

const email = ref('')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

async function submitForgotPassword(): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''

  if (!isValidEmail(email.value)) {
    errorMessage.value = 'Please enter a valid email address'
    return
  }

  loading.value = true
  try {
    const response = await forgotPassword({ email: email.value.trim().toLowerCase() })
    successMessage.value = response.message
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Request failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-container fluid class="login-page pa-0">
    <div class="login-bg"></div>
    <v-row class="login-row ma-0" align="center" justify="center">
      <v-col cols="12" sm="11" md="8" lg="6" xl="5">
        <v-card class="login-shell" rounded="lg" elevation="0">
          <v-card-title class="pt-8 px-8 pb-2">
            <div>
              <div class="auth-brand-head">
                <img src="/equityedge-logo.svg" alt="EquityEdge logo" class="auth-brand-logo" />
                <div>
                  <div class="auth-brand-name">EquityEdge</div>
                  <div class="auth-brand-tag">Insight. Strategy. Growth.</div>
                </div>
              </div>
              <div class="text-overline text-medium-emphasis">Account Recovery</div>
              <h2 class="text-h5 font-weight-bold mb-1">Forgot Password</h2>
              <div class="text-body-2 text-medium-emphasis">
                Enter your registered email. If the account exists, a reset link will be sent.
              </div>
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

            <v-alert
              v-if="successMessage"
              type="success"
              variant="tonal"
              density="comfortable"
              class="mb-4"
              closable
              @click:close="successMessage = ''"
            >
              {{ successMessage }}
            </v-alert>

            <v-text-field
              v-model="email"
              label="Email"
              type="email"
              prepend-inner-icon="mdi-email-outline"
              autocomplete="email"
              @keyup.enter="submitForgotPassword"
            />

            <v-btn
              block
              color="primary"
              size="large"
              :loading="loading"
              :disabled="!email.trim() || !isValidEmail(email)"
              @click="submitForgotPassword"
            >
              Send Reset Link
            </v-btn>

            <div class="text-body-2 text-medium-emphasis text-center mt-4">
              Back to
              <router-link class="signup-link" to="/login">Login</router-link>
            </div>
          </v-card-text>
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
  background: #ffffff;
}

.auth-brand-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.auth-brand-logo {
  width: 54px;
  height: 54px;
  border-radius: 10px;
  border: 1px solid #e2e5ea;
  background: #ffffff;
  object-fit: contain;
}

.auth-brand-name {
  font-family: Manrope, sans-serif;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: 0.01em;
  color: #0f172a;
}

.auth-brand-tag {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: #64748b;
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
</style>
