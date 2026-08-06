<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { resetPassword } from '../services/auth'

const route = useRoute()
const router = useRouter()
const token = ref(String(route.query.token ?? ''))
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const passwordMismatch = computed(
  () => confirmPassword.value.length > 0 && newPassword.value !== confirmPassword.value,
)

const canSubmit = computed(
  () => token.value.trim().length > 0 && newPassword.value.length >= 6 && !passwordMismatch.value,
)

async function submitResetPassword(): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''

  if (passwordMismatch.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  loading.value = true
  try {
    const response = await resetPassword({
      token: token.value.trim(),
      new_password: newPassword.value,
    })
    successMessage.value = response.message
    window.setTimeout(() => {
      void router.replace('/login')
    }, 1200)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Password reset failed'
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
        <v-card class="login-shell" rounded="xl" elevation="14">
          <v-card-title class="pt-8 px-8 pb-2">
            <div>
              <div class="text-overline text-medium-emphasis">Account Recovery</div>
              <h2 class="text-h5 font-weight-bold mb-1">Reset Password</h2>
              <div class="text-body-2 text-medium-emphasis">
                Set a new password for your account.
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
            >
              {{ successMessage }}
            </v-alert>

            <v-text-field
              v-model="token"
              label="Reset Token"
              prepend-inner-icon="mdi-key-outline"
              autocomplete="off"
            />

            <v-text-field
              v-model="newPassword"
              label="New Password"
              type="password"
              prepend-inner-icon="mdi-lock-reset"
              autocomplete="new-password"
              hint="Minimum 6 characters"
              persistent-hint
            />

            <v-text-field
              v-model="confirmPassword"
              label="Confirm New Password"
              type="password"
              prepend-inner-icon="mdi-lock-check-outline"
              autocomplete="new-password"
              :error="passwordMismatch"
              :error-messages="passwordMismatch ? 'Passwords do not match' : ''"
              @keyup.enter="submitResetPassword"
            />

            <v-btn
              block
              color="primary"
              size="large"
              :loading="loading"
              :disabled="!canSubmit"
              @click="submitResetPassword"
            >
              Reset Password
            </v-btn>

            <div class="text-body-2 text-medium-emphasis text-center mt-4">
              Return to
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
    linear-gradient(135deg, rgba(238, 243, 250, 0.28) 0%, rgba(213, 226, 243, 0.28) 100%),
    url('/login-market-grid.svg') center/cover no-repeat,
    radial-gradient(circle at 15% 20%, rgba(255, 217, 61, 0.2) 0%, transparent 34%),
    radial-gradient(circle at 80% 72%, rgba(11, 96, 176, 0.22) 0%, transparent 40%),
    linear-gradient(135deg, #eef3fa 0%, #e4edf8 42%, #d5e2f3 100%);
}

.login-shell {
  position: relative;
  border: 1px solid rgba(31, 47, 70, 0.12);
  overflow: hidden;
  background: rgba(255, 255, 255, 0.97);
}

.signup-link {
  color: #1f4f9a;
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.signup-link:hover {
  text-decoration: underline;
}
</style>
