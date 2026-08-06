<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'

import { useRunsController } from '../composables/useRunsController'

const controller = reactive(useRunsController())
const router = useRouter()
const ACTIVE_RUN_STATUSES = new Set(['queued', 'preparing', 'running', 'cooling_down'])

const totalRuns = computed(() => controller.runsMeta.total)
const activeRuns = computed(() => controller.runs.filter((run) => ACTIVE_RUN_STATUSES.has(run.status)).length)
const completedRuns = computed(
  () => controller.runs.filter((run) => run.status === 'completed' || run.status === 'partial_completed').length,
)
const failedRuns = computed(() => controller.runs.filter((run) => run.status === 'failed').length)
const completionRate = computed(() => {
  if (totalRuns.value <= 0) {
    return 0
  }
  return Math.round((completedRuns.value / totalRuns.value) * 100)
})

function goToScreener(): void {
  void router.push('/screener')
}

function goToJournal(): void {
  void router.push('/journal')
}
</script>

<template>
  <div class="dashboard-shell">
    <v-row>
      <v-col cols="12" md="6" xl="3">
        <v-sheet class="dashboard-kpi-card" rounded="xl">
          <div class="dashboard-kpi-head">
            <span class="dashboard-kpi-label">Total Runs</span>
            <v-icon size="18" color="primary">mdi-counter</v-icon>
          </div>
          <div class="dashboard-kpi-value">{{ totalRuns }}</div>
          <div class="dashboard-kpi-foot">All historical screening cycles</div>
        </v-sheet>
      </v-col>

      <v-col cols="12" md="6" xl="3">
        <v-sheet class="dashboard-kpi-card" rounded="xl">
          <div class="dashboard-kpi-head">
            <span class="dashboard-kpi-label">Active Runs</span>
            <v-icon size="18" color="warning">mdi-pulse</v-icon>
          </div>
          <div class="dashboard-kpi-value">{{ activeRuns }}</div>
          <div class="dashboard-kpi-foot">Currently queued or processing</div>
        </v-sheet>
      </v-col>

      <v-col cols="12" md="6" xl="3">
        <v-sheet class="dashboard-kpi-card" rounded="xl">
          <div class="dashboard-kpi-head">
            <span class="dashboard-kpi-label">Completed / Failed</span>
            <v-icon size="18" color="success">mdi-check-decagram-outline</v-icon>
          </div>
          <div class="dashboard-kpi-value">{{ completedRuns }} / {{ failedRuns }}</div>
          <div class="dashboard-kpi-foot">Execution outcome distribution</div>
        </v-sheet>
      </v-col>

      <v-col cols="12" md="6" xl="3">
        <v-sheet class="dashboard-kpi-card" rounded="xl">
          <div class="dashboard-kpi-head">
            <span class="dashboard-kpi-label">Completion Rate</span>
            <v-icon size="18" color="info">mdi-chart-donut</v-icon>
          </div>
          <div class="dashboard-kpi-value">{{ completionRate }}%</div>
          <div class="dashboard-kpi-foot">Based on total run history</div>
        </v-sheet>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12" lg="8">
        <v-card class="dashboard-core-card" rounded="xl">
          <v-card-title class="dashboard-card-title">
            <div>
              <div class="dashboard-card-kicker">Command View</div>
              <div class="dashboard-card-heading">Consolidated Analytics Console</div>
              <div class="dashboard-card-subheading">Cross-module intelligence, signal quality trend, and execution performance context.</div>
            </div>
          </v-card-title>

          <v-card-text>
            <div class="dashboard-insight-grid">
              <v-sheet class="dashboard-insight-tile" rounded="lg">
                <div class="dashboard-insight-title">Pipeline Status</div>
                <div class="dashboard-insight-copy">Upload, validation, run queue, and result exports are centralized under Screener.</div>
              </v-sheet>

              <v-sheet class="dashboard-insight-tile" rounded="lg">
                <div class="dashboard-insight-title">Execution Memory</div>
                <div class="dashboard-insight-copy">Trading Journal remains the record layer for entries, exits, and post-trade reasoning.</div>
              </v-sheet>

              <v-sheet class="dashboard-insight-tile" rounded="lg">
                <div class="dashboard-insight-title">Upcoming Modules</div>
                <div class="dashboard-insight-copy">Performance charts, signal quality heatmaps, and portfolio posture snapshots.</div>
              </v-sheet>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="4">
        <v-card class="dashboard-actions-card" rounded="xl">
          <v-card-title class="dashboard-card-title">
            <div>
              <div class="dashboard-card-kicker">Quick Access</div>
              <div class="dashboard-card-heading">Operational Shortcuts</div>
              <div class="dashboard-card-subheading">Move directly to high-frequency workflows.</div>
            </div>
          </v-card-title>

          <v-card-text>
            <div class="dashboard-action-grid">
              <v-btn
                class="dashboard-action-btn"
                variant="flat"
                color="primary"
                prepend-icon="mdi-file-chart-outline"
                size="large"
                @click="goToScreener"
              >
                Open Screener
              </v-btn>

              <v-btn
                class="dashboard-action-btn"
                variant="tonal"
                color="secondary"
                prepend-icon="mdi-notebook-edit-outline"
                size="large"
                @click="goToJournal"
              >
                Open Trading Journal
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
