<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useRunsController } from '../composables/useRunsController'

const controller = reactive(useRunsController())
const router = useRouter()
const dashboardDownloadConfirmOpen = ref(false)
const dismissedRunId = ref('')
const DISMISSED_RUN_STORAGE_KEY = 'dashboard.dismissedRunId'

const quickSteps = [
  {
    title: 'Step 1. Validate CSV',
    detail: 'Upload your sheet and verify headers/rows before compute starts.',
  },
  {
    title: 'Step 2. Run Engine',
    detail: 'Start processing with refresh toggle and watch live progress.',
  },
  {
    title: 'Step 3. Review + Export',
    detail: 'Review symbol-level results, monitor runs, and export filtered output.',
  },
]

function onFileSelected(files: File[] | File | null): void {
  const nextFile = Array.isArray(files) ? (files[0] ?? null) : files
  controller.selectedFile = nextFile
  controller.clearUploadWorkflowState()
}

const workflowStep = computed(() => {
  if (!controller.uploadResult) {
    return 1
  }
  if (!controller.uploadResult.valid) {
    return 1
  }
  return 2
})

const canExecuteWorkflow = computed(() => !!controller.uploadResult?.valid && !!controller.uploadResult?.upload_id)

const isSelectedRunActive = computed(() => {
  const status = controller.selectedRun?.status
  return status === 'queued' || status === 'preparing' || status === 'running' || status === 'cooling_down'
})

const selectedRunStatusTitle = computed(() => {
  const status = controller.selectedRun?.status
  if (status === 'completed') {
    return 'Run Completed'
  }
  if (status === 'partial_completed') {
    return 'Run Partially Completed'
  }
  if (status === 'failed') {
    return 'Run Failed'
  }
  if (status === 'stopped') {
    return 'Run Stopped'
  }
  return 'Live Run Status'
})

const showSelectedRunStatus = computed(() => {
  const run = controller.selectedRun
  if (!run) {
    return false
  }
  if (isSelectedRunActive.value) {
    return true
  }
  return dismissedRunId.value !== run.run_id
})

async function runValidatedWorkflow(): Promise<void> {
  if (!canExecuteWorkflow.value) {
    return
  }

  await controller.startValidatedWorkflowRun()
}

function goToRuns(): void {
  void router.push('/runs')
}

function requestDashboardRunDownload(): void {
  if (!controller.canDownloadCsv) {
    return
  }
  dashboardDownloadConfirmOpen.value = true
}

function confirmDashboardRunDownload(): void {
  dashboardDownloadConfirmOpen.value = false
  controller.downloadSelectedRunCsv()
}

function dismissSelectedRunStatus(): void {
  if (!controller.selectedRun) {
    return
  }
  dismissedRunId.value = controller.selectedRun.run_id
  try {
    window.localStorage.setItem(DISMISSED_RUN_STORAGE_KEY, dismissedRunId.value)
  } catch {
    // Ignore storage errors and keep in-memory fallback behavior.
  }
}

onMounted(() => {
  try {
    dismissedRunId.value = window.localStorage.getItem(DISMISSED_RUN_STORAGE_KEY) ?? ''
  } catch {
    dismissedRunId.value = ''
  }
})
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card class="workflow-guide-card mb-4">
        <v-card-title class="card-heading d-flex justify-space-between align-center">
          <div>
            <div>Workflow Guide</div>
            <div class="text-body-2 text-medium-emphasis">Use this sequence for fastest and safest execution.</div>
          </div>
        </v-card-title>
        <v-card-text>
          <v-row>
            <v-col v-for="(step, index) in quickSteps" :key="step.title" cols="12" md="4">
              <v-sheet rounded="lg" class="quick-step-card">
                <div class="quick-step-index">{{ index + 1 }}</div>
                <div class="quick-step-title">{{ step.title }}</div>
                <div class="text-body-2 text-medium-emphasis">{{ step.detail }}</div>
              </v-sheet>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <v-row>
    <v-col cols="12">
      <v-card class="h-100 workflow-card">
        <v-card-title class="d-flex flex-column align-start ga-1 card-heading">
          <span>Screening Run Setup</span>
          <span class="text-body-2 text-medium-emphasis">Validate the input list, then launch and monitor the screening run.</span>
        </v-card-title>
        <v-card-text>
          <v-stepper :model-value="workflowStep" alt-labels flat class="mb-4 workflow-stepper">
            <v-stepper-header>
              <v-stepper-item :value="1" title="Validate CSV" />
              <v-divider />
              <v-stepper-item :value="2" title="Run & Process" :complete="!!controller.selectedRunId" />
            </v-stepper-header>
          </v-stepper>

          <v-sheet class="info-band mb-4" rounded="lg">
            <div class="text-body-2 text-medium-emphasis">Step 1: Upload and validate strict schema.</div>
            <div class="text-body-2 text-medium-emphasis">Allowed headers: Name, BSE Code, NSE Code, ISIN Code, Industry Group</div>
          </v-sheet>

          <v-alert v-if="controller.hasActiveRun" type="info" variant="tonal" class="mb-3">
            A run is currently {{ controller.activeRun?.status }} ({{ controller.activeRun?.run_id.slice(0, 8) }}).
            You can start a new run only after it completes or is stopped.
          </v-alert>

          <v-sheet v-if="showSelectedRunStatus && controller.selectedRun" class="run-status-strip mb-4" rounded="lg">
            <div class="run-status-strip-header">
              <div class="d-flex align-center ga-2 flex-wrap">
                <span class="run-status-title">{{ selectedRunStatusTitle }}</span>
                <v-chip size="small" variant="tonal">{{ controller.selectedRun?.run_id?.slice(0, 8) || '' }}</v-chip>
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="
                    controller.selectedRun?.status === 'completed'
                      ? 'success'
                      : controller.selectedRun?.status === 'partial_completed'
                        ? 'warning'
                      : controller.selectedRun?.status === 'failed'
                        ? 'error'
                        : controller.selectedRun?.status === 'stopped'
                          ? 'warning'
                          : 'info'
                  "
                >
                  {{ controller.selectedRun?.status || '-' }}
                </v-chip>
              </div>
              <div class="d-flex align-center ga-2 flex-wrap">
                <v-btn variant="tonal" size="small" color="primary" @click="goToRuns">Monitor In Runs</v-btn>
                <v-btn
                  variant="tonal"
                  size="small"
                  :disabled="!controller.canDownloadCsv"
                  @click="requestDashboardRunDownload"
                >
                  Download CSV
                </v-btn>
                <v-btn
                  v-if="!isSelectedRunActive"
                  variant="text"
                  size="small"
                  color="secondary"
                  icon="mdi-close"
                  @click="dismissSelectedRunStatus"
                />
              </div>
            </div>
            <div class="run-status-strip-meta">
              <span>{{ controller.selectedRun?.processed || 0 }} / {{ controller.selectedRun?.total || 0 }} processed</span>
              <span>{{ controller.progressPct }}%</span>
            </div>
            <v-progress-linear :model-value="controller.progressPct" color="primary" height="10" rounded />
          </v-sheet>

          <v-sheet class="upload-control-strip mb-2" rounded="lg">
            <div class="upload-control-row">
              <v-file-input
                class="workflow-file-input"
                label="Select CSV File"
                accept=".csv,text/csv"
                prepend-icon="mdi-file-upload-outline"
                variant="outlined"
                density="comfortable"
                show-size
                hide-details
                @update:model-value="onFileSelected"
              />
              <div class="workflow-actions d-flex ga-2 flex-wrap">
                <v-btn class="action-btn" :loading="controller.uploading" size="large" @click="controller.validateUpload">
                  Validate File
                </v-btn>
                <v-btn class="action-btn" variant="text" color="secondary" @click="controller.clearUploadWorkflowState">
                  Clear Validation
                </v-btn>
              </div>
            </div>
          </v-sheet>

          <v-alert
            v-if="controller.uploadError"
            type="error"
            variant="tonal"
            class="mt-3"
            closable
            @click:close="controller.uploadError = ''"
          >
            {{ controller.uploadError }}
          </v-alert>

          <v-alert
            v-if="controller.uploadResult"
            :type="controller.uploadResult.valid ? 'success' : 'warning'"
            variant="tonal"
            class="mt-3"
          >
            Validation: {{ controller.uploadResult.valid ? 'PASS' : 'FAIL' }}
            <br />
            Rows: {{ controller.uploadResult.accepted_rows }} accepted / {{ controller.uploadResult.total_rows }} total
            <template v-if="controller.uploadResult.rejected_rows > 0">
              <br />Rejected rows: {{ controller.uploadResult.rejected_rows }}
            </template>
            <template v-if="controller.uploadResult.missing_headers.length > 0">
              <br />Missing headers: {{ controller.uploadResult.missing_headers.join(', ') }}
            </template>
            <template v-if="controller.uploadResult.unexpected_headers.length > 0">
              <br />Unexpected headers: {{ controller.uploadResult.unexpected_headers.join(', ') }}
            </template>
            <template v-if="controller.uploadResult.errors.length > 0">
              <br />{{ controller.uploadResult.errors.join(' | ') }}
            </template>
          </v-alert>

          <template v-if="controller.uploadResult?.valid">
            <v-divider class="my-4" />
            <p class="text-body-2 text-medium-emphasis mb-2">
              Validation completed. You can now run and process this same CSV directly.
            </p>
            <v-sheet class="pa-3 rounded-lg border mb-2 validated-panel">
              <div class="text-body-2"><strong>File:</strong> {{ controller.uploadResult.filename }}</div>
              <div class="text-body-2"><strong>Accepted rows:</strong> {{ controller.uploadResult.accepted_rows }}</div>
              <div class="text-body-2"><strong>Rejected rows:</strong> {{ controller.uploadResult.rejected_rows }}</div>
            </v-sheet>

            <div class="mt-2 d-flex ga-2 align-center flex-wrap">
              <v-btn
                class="action-btn"
                :loading="controller.submitting"
                :disabled="!canExecuteWorkflow || controller.hasActiveRun"
                size="large"
                @click="runValidatedWorkflow"
              >
                Run And Process CSV
              </v-btn>
              <v-btn class="action-btn" variant="tonal" color="primary" @click="goToRuns">Monitor In Runs</v-btn>
              <v-btn class="action-btn" variant="tonal" color="secondary" @click="controller.validateUpload">Re-Validate</v-btn>
            </div>
          </template>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <v-dialog v-model="dashboardDownloadConfirmOpen" max-width="460">
    <v-card>
      <v-card-title>Download Run CSV</v-card-title>
      <v-card-text>Are you sure you want to download this run CSV?</v-card-text>
      <v-card-actions class="justify-end">
        <v-btn variant="text" color="secondary" @click="dashboardDownloadConfirmOpen = false">Cancel</v-btn>
        <v-btn variant="flat" color="primary" @click="confirmDashboardRunDownload">Yes, Download</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
