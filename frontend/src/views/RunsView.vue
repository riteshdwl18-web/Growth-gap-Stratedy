<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useRunsController } from '../composables/useRunsController'

const controller = reactive(useRunsController())
const router = useRouter()

const runHeaders = [
  { title: 'Run ID', key: 'run_id' },
  { title: 'Status', key: 'status' },
  { title: 'Stage', key: 'stage' },
  { title: 'Universe', key: 'input_universe' },
  { title: 'Processed', key: 'processed' },
  { title: 'Retries', key: 'retry_count' },
  { title: 'PASS', key: 'pass_count' },
  { title: 'FAIL', key: 'fail_count' },
  { title: 'Skipped', key: 'skipped_count' },
  { title: 'Created', key: 'created_at' },
  { title: 'Stopped At', key: 'stopped_at' },
  { title: 'Actions', key: 'actions', sortable: false },
]

const runStatusOptions = [
  { title: 'All Statuses', value: 'all' },
  { title: 'Queued', value: 'queued' },
  { title: 'Preparing', value: 'preparing' },
  { title: 'Running', value: 'running' },
  { title: 'Cooling Down', value: 'cooling_down' },
  { title: 'Completed', value: 'completed' },
  { title: 'Partial Completed', value: 'partial_completed' },
  { title: 'Failed', value: 'failed' },
  { title: 'Stopped', value: 'stopped' },
]

const runSortOptions = [
  { title: 'Created Time', value: 'created_at' },
  { title: 'Status', value: 'status' },
  { title: 'Stage', value: 'stage' },
  { title: 'Universe', value: 'input_universe' },
  { title: 'Processed', value: 'processed' },
  { title: 'Retry Count', value: 'retry_count' },
  { title: 'PASS Count', value: 'pass_count' },
  { title: 'FAIL Count', value: 'fail_count' },
  { title: 'Skipped Count', value: 'skipped_count' },
]

const ACTIVE_RUN_STATUSES = new Set(['queued', 'preparing', 'running', 'cooling_down'])
const activeRuns = computed(() => controller.runs.filter((run) => ACTIVE_RUN_STATUSES.has(run.status)).length)
const completedRuns = computed(
  () => controller.runs.filter((run) => run.status === 'completed' || run.status === 'partial_completed').length,
)
const failedRuns = computed(() => controller.runs.filter((run) => run.status === 'failed').length)

const actionConfirmOpen = ref(false)
const actionConfirmTitle = ref('')
const actionConfirmMessage = ref('')
const actionConfirmLoading = ref(false)
const actionConfirmTask = ref<null | (() => Promise<void> | void)>(null)

function onRunsPageSizeChange(nextValue: number | string | null): void {
  controller.setRunsPageSize(Number(nextValue ?? 10))
}

function clearRunsSearch(): void {
  controller.runsQuery.search = ''
  controller.applyRunsFilters()
}

function rangeLabel(page: number, pageSize: number, pageItems: number, total: number): string {
  if (total <= 0 || pageItems <= 0) {
    return '0 of 0'
  }
  const start = (page - 1) * pageSize + 1
  const end = start + pageItems - 1
  return `${start}-${end} of ${total}`
}

function formatLocalDateTime(value: string | null | undefined): string {
  const rawValue = String(value ?? '').trim()
  if (!rawValue) {
    return ''
  }

  const hasTimeZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(rawValue)
  const normalized = hasTimeZone ? rawValue : `${rawValue}Z`
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return rawValue
  }
  return parsed.toLocaleString()
}

function openActionConfirm(
  title: string,
  message: string,
  task: () => Promise<void> | void,
): void {
  actionConfirmTitle.value = title
  actionConfirmMessage.value = message
  actionConfirmTask.value = task
  actionConfirmOpen.value = true
}

function closeActionConfirm(): void {
  actionConfirmOpen.value = false
  actionConfirmLoading.value = false
  actionConfirmTask.value = null
}

async function confirmAction(): Promise<void> {
  if (!actionConfirmTask.value) {
    closeActionConfirm()
    return
  }

  actionConfirmLoading.value = true
  try {
    await actionConfirmTask.value()
  } finally {
    closeActionConfirm()
  }
}

function confirmAndStop(runId: string): void {
  openActionConfirm(
    'Stop Run',
    'Are you sure you want to stop this run now? It will halt after the current symbol finishes.',
    async () => {
      await controller.stopRun(runId)
    },
  )
}

function downloadRunCsv(runId: string): void {
  openActionConfirm(
    'Download Run CSV',
    'Are you sure you want to download this run CSV?',
    () => {
      window.open(`${controller.API_BASE_URL}/api/runs/${runId}/download.csv`, '_blank')
    },
  )
}

function openRunDetails(runId: string): void {
  controller.setSelectedRun(runId)
  void router.push(`/runs/${runId}`)
}

function openRunDetailsForRetry(runId: string): void {
  controller.setSelectedRun(runId)
  void router.push({ path: `/runs/${runId}`, query: { retry: '1' } })
}

function retryableCount(run: { skipped_count?: number }): number {
  return Number(run.skipped_count || 0)
}
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card class="mb-4 runs-card">
        <v-card-title class="d-flex justify-space-between align-center card-heading">
          <div>
            <div>Recent Runs</div>
            <div class="text-body-2 text-medium-emphasis">Track status, stop active tasks, and open any run result set</div>
          </div>
        </v-card-title>

        <v-card-text>
          <v-sheet class="info-band mb-3" rounded="lg">
            <div class="d-flex ga-2 flex-wrap align-center">
              <v-chip size="small" color="primary" variant="tonal">Step 2: Monitor Runs</v-chip>
              <v-chip size="small" color="info" variant="tonal">Active {{ activeRuns }}</v-chip>
              <v-chip size="small" color="success" variant="tonal">Completed {{ completedRuns }}</v-chip>
              <v-chip size="small" color="error" variant="tonal">Failed {{ failedRuns }}</v-chip>
            </div>
          </v-sheet>

          <v-alert
            v-if="controller.errorMessage"
            type="error"
            variant="tonal"
            class="mb-3"
            closable
            @click:close="controller.errorMessage = ''"
          >
            {{ controller.errorMessage }}
          </v-alert>

          <v-sheet class="filter-band mb-3" rounded="lg">
            <div class="text-body-2 text-medium-emphasis">Filter, sort, and paginate runs from server-side data.</div>
          </v-sheet>

          <v-row class="mb-2">
            <v-col cols="12" md="4">
              <v-text-field
                v-model="controller.runsQuery.search"
                label="Search runs"
                placeholder="Run ID, status, universe"
                prepend-inner-icon="mdi-magnify"
                clear-icon="mdi-close-circle"
                clearable
                persistent-clear
                @click:clear="clearRunsSearch"
                @keyup.enter="controller.applyRunsFilters"
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="controller.runsQuery.status"
                :items="runStatusOptions"
                item-title="title"
                item-value="value"
                label="Status"
                @update:model-value="controller.applyRunsFilters"
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-text-field
                v-model="controller.runsQuery.created_from"
                label="Created From"
                type="date"
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-text-field
                v-model="controller.runsQuery.created_to"
                label="Created To"
                type="date"
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="controller.runsQuery.sort_by"
                :items="runSortOptions"
                item-title="title"
                item-value="value"
                label="Sort by"
                @update:model-value="controller.applyRunsFilters"
              />
            </v-col>
          </v-row>

          <v-data-table
            class="runs-table polished-table"
            :headers="runHeaders"
            :items="controller.runs"
            item-value="run_id"
            density="compact"
            hide-default-footer
            :items-per-page="-1"
          >
            <template #item.run_id="{ item }">
              <a href="#" class="run-id" @click.prevent="openRunDetails(item.run_id)">
                {{ item.run_id.slice(0, 8) }}
              </a>
            </template>

            <template #item.status="{ item }">
              <div class="d-flex align-center ga-1 flex-wrap">
                <v-chip
                  size="small"
                  :color="
                    item.status === 'completed' || item.status === 'partial_completed'
                      ? 'success'
                      : item.status === 'failed'
                        ? 'error'
                        : item.status === 'stopped'
                          ? 'warning'
                          : 'info'
                  "
                  variant="tonal"
                >
                  {{ item.status }}
                </v-chip>
                <v-chip
                  v-if="retryableCount(item) > 0"
                  size="x-small"
                  color="secondary"
                  variant="outlined"
                  style="cursor: pointer"
                  @click="openRunDetailsForRetry(item.run_id)"
                >
                  Retry {{ retryableCount(item) }}
                </v-chip>
                <v-chip
                  v-if="Number(item.retry_count || 0) > 0"
                  size="x-small"
                  color="primary"
                  variant="outlined"
                >
                  Retries {{ item.retry_count }}
                </v-chip>
              </div>
            </template>

            <template #item.stage="{ item }">{{ item.stage || item.status || '-' }}</template>
            <template #item.retry_count="{ item }">{{ item.retry_count || 0 }}</template>

            <template #item.processed="{ item }">{{ item.processed }} / {{ item.total }}</template>
            <template #item.created_at="{ item }">{{ formatLocalDateTime(item.created_at) }}</template>
            <template #item.stopped_at="{ item }">{{ formatLocalDateTime(item.stopped_at) }}</template>

            <template #item.actions="{ item }">
              <div class="table-action-group">
                <v-tooltip text="View run details" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-eye-outline"
                      size="small"
                      variant="tonal"
                      color="primary"
                      @click="openRunDetails(item.run_id)"
                    />
                  </template>
                </v-tooltip>

                <v-tooltip text="Download run CSV" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-file-download-outline"
                      size="small"
                      variant="tonal"
                      color="secondary"
                      :disabled="item.status !== 'completed' && item.status !== 'partial_completed'"
                      @click="downloadRunCsv(item.run_id)"
                    />
                  </template>
                </v-tooltip>

                <v-tooltip text="Stop run" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-stop-circle-outline"
                      size="small"
                      color="error"
                      variant="tonal"
                      :disabled="!ACTIVE_RUN_STATUSES.has(item.status)"
                      @click="confirmAndStop(item.run_id)"
                    />
                  </template>
                </v-tooltip>
              </div>
            </template>

            <template #no-data>No runs yet. Start a run from Screener.</template>
          </v-data-table>

          <div class="d-flex justify-space-between align-center mt-3 flex-wrap ga-3">
            <div class="text-body-2 text-medium-emphasis">
              {{ rangeLabel(controller.runsMeta.page, controller.runsMeta.page_size, controller.runs.length, controller.runsMeta.total) }}
            </div>
            <div class="d-flex align-center ga-3">
              <v-select
                label="Rows"
                :items="[10, 25, 50]"
                :model-value="controller.runsQuery.page_size"
                style="max-width: 120px"
                @update:model-value="onRunsPageSizeChange"
              />
              <v-pagination
                :model-value="controller.runsMeta.page"
                :length="controller.runsMeta.total_pages"
                density="comfortable"
                @update:model-value="controller.setRunsPage"
              />
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <v-dialog v-model="actionConfirmOpen" max-width="460">
    <v-card>
      <v-card-title>{{ actionConfirmTitle }}</v-card-title>
      <v-card-text>{{ actionConfirmMessage }}</v-card-text>
      <v-card-actions class="justify-end">
        <v-btn variant="text" color="secondary" :disabled="actionConfirmLoading" @click="closeActionConfirm">Cancel</v-btn>
        <v-btn variant="flat" color="primary" :loading="actionConfirmLoading" @click="confirmAction">Yes, Continue</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
