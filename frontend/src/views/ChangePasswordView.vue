<script setup lang="ts">
import { computed, ref } from 'vue'

import { changePassword } from '../services/auth'

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const newPasswordMismatch = computed(
  () => confirmPassword.value.length > 0 && confirmPassword.value !== newPassword.value,
)

const canSubmit = computed(
  () =>
    currentPassword.value.length > 0 &&
    newPassword.value.length >= 6 &&
    confirmPassword.value.length > 0 &&
    !newPasswordMismatch.value,
)

async function submit(): Promise<void> {
  errorMessage.value = ''
  successMessage.value = ''

  if (newPasswordMismatch.value) {
    errorMessage.value = 'New password and confirm password must match'
    return
  }

  loading.value = true
  try {
    const result = await changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    successMessage.value = result.message
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Password change failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-card class="pa-4 pa-md-6" rounded="lg" elevation="0">
    <div class="text-overline text-medium-emphasis mb-1">Account Security</div>
    <h2 class="text-h5 font-weight-bold mb-2">Change Password</h2>
    <p class="text-body-2 text-medium-emphasis mb-5">
      Update your account password. New password must be at least 6 characters.
    </p>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
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
      class="mb-4"
      closable
      @click:close="successMessage = ''"
    >
      {{ successMessage }}
    </v-alert>

    <v-row>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="currentPassword"
          label="Current Password"
          type="password"
          autocomplete="current-password"
          prepend-inner-icon="mdi-lock-outline"
        />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="newPassword"
          label="New Password"
          type="password"
          autocomplete="new-password"
          prepend-inner-icon="mdi-lock-reset"
          hint="Minimum 6 characters"
          persistent-hint
        />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="confirmPassword"
          label="Confirm New Password"
          type="password"
          autocomplete="new-password"
          prepend-inner-icon="mdi-lock-check-outline"
          :error="newPasswordMismatch"
          :error-messages="newPasswordMismatch ? 'Passwords do not match' : ''"
          @keyup.enter="submit"
        />
      </v-col>
    </v-row>

    <div class="d-flex justify-end mt-2">
      <v-btn color="primary" :loading="loading" :disabled="!canSubmit" @click="submit">
        Update Password
      </v-btn>
    </div>
  </v-card>
</template>

<style scoped>
p {
  max-width: 72ch;
}
</style>
