<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useRunsController } from '../composables/useRunsController'
import type { FavoriteResultsFilterQuery } from '../composables/useRunsController'

const controller = reactive(useRunsController())
const route = useRoute()
const router = useRouter()
const detailDrawerOpen = ref(false)
const selectedResult = ref<Record<string, unknown> | null>(null)
const downloadConfirmOpen = ref(false)
const filterDialogOpen = ref(false)
const copyToastOpen = ref(false)
const copyToastMessage = ref('')
const liveRefreshRequestedAt = ref('')
const favoriteDialogOpen = ref(false)
const favoriteName = ref('')
const favoriteSetAsDefault = ref(false)
const favoriteBusy = ref(false)
const favoriteError = ref('')
const favoriteDialogUsesFilterDraft = ref(false)
const favoriteRenameDialogOpen = ref(false)
const favoriteRenameName = ref('')
const favoriteRenameSetAsDefault = ref(false)
const favoriteRenameReplaceQuery = ref(false)
const favoriteRenameBusy = ref(false)
const favoriteRenameError = ref('')
const deleteFavoriteConfirmOpen = ref(false)
const runActionError = ref('')
const cooldownNowMs = ref(Date.now())
let cooldownTickerHandle: number | undefined
const ALL_LIST_OPTION_VALUE = '__all_list__'
const INDUSTRY_ALL_VALUE = '__all__'
const filterDraft = reactive({
  final_status: 'all',
  market_cap_min: '',
  market_cap_max: '',
  industry_groups: [] as string[],
  total_2y_growth_min: '',
  total_2y_growth_max: '',
  ttm_vs_end_fy_min: '',
  ttm_vs_end_fy_max: '',
  combined_growth_min: '',
  combined_growth_max: '',
  roce_min: '',
  roce_max: '',
  away_min: '',
  away_max: '',
})

const MIN_TOTAL_GROWTH = 32.25
const MIN_TTM_GROWTH = 5
const MIN_COMBINED_GROWTH = MIN_TOTAL_GROWTH + MIN_TTM_GROWTH
const ACTIVE_RUN_STATUSES = new Set(['queued', 'preparing', 'running', 'cooling_down'])

const resultHeaders = [
  { title: 'Name', key: 'name' },
  { title: 'Symbol', key: 'symbol' },
  { title: 'Mark.Cap', key: 'market_cap_cr' },
  { title: 'Industry Group', key: 'industry_group' },
  { title: 'Base Rev (Cr)', key: 'base_rev_cr' },
  { title: 'End Rev (Cr)', key: 'end_rev_cr' },
  { title: 'Total 2Y %', key: 'total_2y_growth_pct' },
  { title: 'TTM Rev (Cr)', key: 'ttm_rev_cr' },
  { title: 'TTM vs End FY %', key: 'ttm_vs_end_fy_pct' },
  { title: 'Combined %', key: 'combined_growth_pct' },
  { title: 'Final', key: 'final_status' },
  { title: 'Live Price', key: 'current_price' },
  { title: 'Entry Price', key: 'price_2y_ago' },
  { title: '% Away', key: 'price_2y_change_pct' },
  { title: 'ROCE %', key: 'roce_pct' },
  { title: 'Error', key: 'error' },
  { title: 'Actions', key: 'actions', sortable: false },
]

const resultStatusOptions = [
  { title: 'All Result Statuses', value: 'all' },
  { title: 'PASS', value: 'pass' },
  { title: 'FAIL', value: 'fail' },
  { title: 'SKIPPED', value: 'skipped' },
]

function parseResultFilterFromRouteQuery(): 'all' | 'pass' | 'fail' | 'skipped' | null {
  const value = String(route.query.result ?? '').trim().toLowerCase()
  if (value === 'all' || value === 'pass' || value === 'fail' || value === 'skipped') {
    return value
  }
  return null
}

function applyResultFilterFromRouteQuery(options?: { fetch?: boolean }): void {
  const routeFilter = parseResultFilterFromRouteQuery()
  if (!routeFilter) {
    return
  }

  if (controller.resultsQuery.final_status !== routeFilter) {
    controller.resultsQuery.final_status = routeFilter
  }

  if (options?.fetch === false) {
    return
  }

  controller.applyResultsFilters()
}

const resultSortOptions = [
  { title: 'Name', value: 'name' },
  { title: 'Symbol', value: 'symbol' },
  { title: 'Mark.Cap', value: 'market_cap_cr' },
  { title: 'Industry Group', value: 'industry_group' },
  { title: 'Base Rev (Cr)', value: 'base_rev_cr' },
  { title: 'End Rev (Cr)', value: 'end_rev_cr' },
  { title: 'Total 2Y %', value: 'total_2y_growth_pct' },
  { title: 'TTM Rev (Cr)', value: 'ttm_rev_cr' },
  { title: 'TTM vs End FY %', value: 'ttm_vs_end_fy_pct' },
  { title: 'Combined %', value: 'combined_growth_pct' },
  { title: 'Final Status', value: 'final_status' },
  { title: 'Live Price', value: 'current_price' },
  { title: 'Entry Price', value: 'price_2y_ago' },
  { title: '% Away', value: 'price_2y_change_pct' },
  { title: 'ROCE %', value: 'roce_pct' },
  { title: 'Error', value: 'error' },
]

async function applyRouteRunId(): Promise<void> {
  const runId = String(route.params.runId ?? '').trim()
  if (!runId) {
    return
  }
  controller.setSelectedRun(runId, { fetch: false })
  applyResultFilterFromRouteQuery({ fetch: false })
  await controller.preloadResultsWithFavorite(runId)
}

function openFavoriteDialog(): void {
  favoriteError.value = ''
  favoriteName.value = ''
  favoriteSetAsDefault.value = false
  favoriteDialogUsesFilterDraft.value = false
  favoriteDialogOpen.value = true
}

function buildFavoriteQueryFromDraft(): FavoriteResultsFilterQuery {
  return {
    search: controller.resultsQuery.search,
    final_status: filterDraft.final_status,
    market_cap_min: filterDraft.market_cap_min.trim(),
    market_cap_max: filterDraft.market_cap_max.trim(),
    industry_group: normalizeIndustrySelection(filterDraft.industry_groups, []).includes(INDUSTRY_ALL_VALUE)
      ? ''
      : normalizeIndustrySelection(filterDraft.industry_groups, []).join(','),
    total_2y_growth_min: filterDraft.total_2y_growth_min.trim(),
    total_2y_growth_max: filterDraft.total_2y_growth_max.trim(),
    ttm_vs_end_fy_min: filterDraft.ttm_vs_end_fy_min.trim(),
    ttm_vs_end_fy_max: filterDraft.ttm_vs_end_fy_max.trim(),
    combined_growth_min: filterDraft.combined_growth_min.trim(),
    combined_growth_max: filterDraft.combined_growth_max.trim(),
    roce_min: filterDraft.roce_min.trim(),
    roce_max: filterDraft.roce_max.trim(),
    away_min: filterDraft.away_min.trim(),
    away_max: filterDraft.away_max.trim(),
    sort_by: controller.resultsQuery.sort_by,
    sort_order: controller.resultsQuery.sort_order,
    page_size: controller.resultsQuery.page_size,
  }
}

function openFavoriteDialogFromFilterPopup(): void {
  favoriteError.value = ''
  favoriteName.value = ''
  favoriteSetAsDefault.value = false
  favoriteDialogUsesFilterDraft.value = true
  favoriteDialogOpen.value = true
}

async function saveOrCreateFavoriteFromFilterPopup(): Promise<void> {
  const selected = controller.favoriteResultsFilters.find(
    (item) => item.filter_id === controller.activeFavoriteFilterId,
  )

  if (!selected) {
    openFavoriteDialogFromFilterPopup()
    return
  }

  favoriteBusy.value = true
  try {
    await controller.updateFavoriteResultsFilter(
      selected.filter_id,
      selected.name,
      selected.is_default,
      buildFavoriteQueryFromDraft(),
    )
    filterDialogOpen.value = false
  } catch (err) {
    favoriteError.value = err instanceof Error ? err.message : 'Failed to update favorite filter'
    openFavoriteDialogFromFilterPopup()
  } finally {
    favoriteBusy.value = false
  }
}

async function saveFavoriteFilter(): Promise<void> {
  favoriteError.value = ''
  const trimmed = favoriteName.value.trim()
  if (!trimmed) {
    favoriteError.value = 'Favorite name is required'
    return
  }

  favoriteBusy.value = true
  try {
    await controller.saveFavoriteResultsFilterWithQuery(
      trimmed,
      favoriteSetAsDefault.value,
      favoriteDialogUsesFilterDraft.value ? buildFavoriteQueryFromDraft() : undefined,
    )
    favoriteDialogOpen.value = false
    favoriteDialogUsesFilterDraft.value = false
  } catch (err) {
    favoriteError.value = err instanceof Error ? err.message : 'Failed to save favorite filter'
  } finally {
    favoriteBusy.value = false
  }
}

async function applySelectedFavoriteFilter(filterId: string): Promise<void> {
  if (filterId === ALL_LIST_OPTION_VALUE) {
    controller.activeFavoriteFilterId = ALL_LIST_OPTION_VALUE
    resetResultsFilters()
    return
  }
  if (!filterId) {
    return
  }
  await controller.applyFavoriteResultsFilter(filterId)
}

async function setSelectedFavoriteAsDefault(): Promise<void> {
  const selected = controller.favoriteResultsFilters.find(
    (item) => item.filter_id === controller.activeFavoriteFilterId,
  )
  if (!selected) {
    return
  }
  await controller.updateFavoriteResultsFilter(selected.filter_id, selected.name, true)
}

async function deleteSelectedFavoriteFilter(): Promise<void> {
  deleteFavoriteConfirmOpen.value = false
  const selectedId = String(controller.activeFavoriteFilterId || '').trim()
  if (!selectedId) {
    return
  }
  await controller.deleteFavoriteResultsFilter(selectedId)
}

function requestDeleteSelectedFavoriteFilter(): void {
  if (!controller.activeFavoriteFilterId) {
    return
  }
  deleteFavoriteConfirmOpen.value = true
}

function openRenameFavoriteDialog(): void {
  favoriteRenameError.value = ''
  const selected = controller.favoriteResultsFilters.find(
    (item) => item.filter_id === controller.activeFavoriteFilterId,
  )
  if (!selected) {
    return
  }
  favoriteRenameName.value = selected.name
  favoriteRenameSetAsDefault.value = selected.is_default
  favoriteRenameReplaceQuery.value = false
  favoriteRenameDialogOpen.value = true
}

async function renameSelectedFavoriteFilter(): Promise<void> {
  favoriteRenameError.value = ''
  const selected = controller.favoriteResultsFilters.find(
    (item) => item.filter_id === controller.activeFavoriteFilterId,
  )
  if (!selected) {
    favoriteRenameError.value = 'Select a favorite filter first'
    return
  }

  const nextName = favoriteRenameName.value.trim()
  if (!nextName) {
    favoriteRenameError.value = 'Favorite name is required'
    return
  }

  favoriteRenameBusy.value = true
  try {
    await controller.updateFavoriteResultsFilter(
      selected.filter_id,
      nextName,
      favoriteRenameSetAsDefault.value,
      favoriteRenameReplaceQuery.value ? undefined : selected.query,
    )
    favoriteRenameDialogOpen.value = false
  } catch (err) {
    favoriteRenameError.value = err instanceof Error ? err.message : 'Failed to rename favorite filter'
  } finally {
    favoriteRenameBusy.value = false
  }
}

function onResultsPageSizeChange(nextValue: number | string | null): void {
  controller.setResultsPageSize(Number(nextValue ?? 25))
}

function resetResultsFilters(): void {
  controller.resultsQuery.search = ''
  controller.resultsQuery.final_status = 'all'
  controller.resultsQuery.market_cap_min = ''
  controller.resultsQuery.market_cap_max = ''
  controller.resultsQuery.industry_group = ''
  controller.resultsQuery.total_2y_growth_min = ''
  controller.resultsQuery.total_2y_growth_max = ''
  controller.resultsQuery.ttm_vs_end_fy_min = ''
  controller.resultsQuery.ttm_vs_end_fy_max = ''
  controller.resultsQuery.combined_growth_min = ''
  controller.resultsQuery.combined_growth_max = ''
  controller.resultsQuery.roce_min = ''
  controller.resultsQuery.roce_max = ''
  controller.resultsQuery.away_min = ''
  controller.resultsQuery.away_max = ''
  controller.resultsQuery.sort_by = 'name'
  controller.resultsQuery.sort_order = 'asc'
  controller.applyResultsFilters()
}

function parseIndustryGroupsFromQuery(rawValue: string): string[] {
  const groups = rawValue
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value.length > 0)
  return groups
}

function normalizeIndustrySelection(values: string[], previousValues: string[]): string[] {
  const unique = Array.from(
    new Set(values.map((value) => value.trim()).filter((value) => value.length > 0)),
  )

  if (unique.length === 0) {
    return []
  }

  const includesAll = unique.includes(INDUSTRY_ALL_VALUE)
  if (!includesAll) {
    return unique
  }

  if (unique.length === 1) {
    return [INDUSTRY_ALL_VALUE]
  }

  const previousHadAll = previousValues.includes(INDUSTRY_ALL_VALUE)
  if (previousHadAll) {
    // User added specific industries while All was selected: drop All.
    return unique.filter((value) => value !== INDUSTRY_ALL_VALUE)
  }

  // User selected All after picking specific industries: keep only All.
  return [INDUSTRY_ALL_VALUE]
}

function syncDraftFromQuery(): void {
  filterDraft.final_status = controller.resultsQuery.final_status
  filterDraft.market_cap_min = controller.resultsQuery.market_cap_min
  filterDraft.market_cap_max = controller.resultsQuery.market_cap_max
  filterDraft.industry_groups = parseIndustryGroupsFromQuery(controller.resultsQuery.industry_group)
  filterDraft.total_2y_growth_min = controller.resultsQuery.total_2y_growth_min
  filterDraft.total_2y_growth_max = controller.resultsQuery.total_2y_growth_max
  filterDraft.ttm_vs_end_fy_min = controller.resultsQuery.ttm_vs_end_fy_min
  filterDraft.ttm_vs_end_fy_max = controller.resultsQuery.ttm_vs_end_fy_max
  filterDraft.combined_growth_min = controller.resultsQuery.combined_growth_min
  filterDraft.combined_growth_max = controller.resultsQuery.combined_growth_max
  filterDraft.roce_min = controller.resultsQuery.roce_min
  filterDraft.roce_max = controller.resultsQuery.roce_max
  filterDraft.away_min = controller.resultsQuery.away_min
  filterDraft.away_max = controller.resultsQuery.away_max
}

function openFilterDialog(): void {
  syncDraftFromQuery()
  filterDialogOpen.value = true
}

function applyAdvancedFilters(): void {
  const normalized = (value: unknown): string => String(value ?? '').trim()

  controller.resultsQuery.final_status = filterDraft.final_status
  controller.resultsQuery.market_cap_min = normalized(filterDraft.market_cap_min)
  controller.resultsQuery.market_cap_max = normalized(filterDraft.market_cap_max)
  filterDraft.industry_groups = normalizeIndustrySelection(filterDraft.industry_groups, [])
  controller.resultsQuery.industry_group =
    filterDraft.industry_groups.includes(INDUSTRY_ALL_VALUE)
      ? ''
      : filterDraft.industry_groups.join(',')
  controller.resultsQuery.total_2y_growth_min = normalized(filterDraft.total_2y_growth_min)
  controller.resultsQuery.total_2y_growth_max = normalized(filterDraft.total_2y_growth_max)
  controller.resultsQuery.ttm_vs_end_fy_min = normalized(filterDraft.ttm_vs_end_fy_min)
  controller.resultsQuery.ttm_vs_end_fy_max = normalized(filterDraft.ttm_vs_end_fy_max)
  controller.resultsQuery.combined_growth_min = normalized(filterDraft.combined_growth_min)
  controller.resultsQuery.combined_growth_max = normalized(filterDraft.combined_growth_max)
  controller.resultsQuery.roce_min = normalized(filterDraft.roce_min)
  controller.resultsQuery.roce_max = normalized(filterDraft.roce_max)
  controller.resultsQuery.away_min = normalized(filterDraft.away_min)
  controller.resultsQuery.away_max = normalized(filterDraft.away_max)
  filterDialogOpen.value = false
  controller.applyResultsFilters()
}

function clearAdvancedFilters(): void {
  filterDraft.final_status = 'all'
  filterDraft.market_cap_min = ''
  filterDraft.market_cap_max = ''
  filterDraft.industry_groups = []
  filterDraft.total_2y_growth_min = ''
  filterDraft.total_2y_growth_max = ''
  filterDraft.ttm_vs_end_fy_min = ''
  filterDraft.ttm_vs_end_fy_max = ''
  filterDraft.combined_growth_min = ''
  filterDraft.combined_growth_max = ''
  filterDraft.roce_min = ''
  filterDraft.roce_max = ''
  filterDraft.away_min = ''
  filterDraft.away_max = ''
}

function onIndustryGroupsSelectionChange(values: string[] | null): void {
  const previousValues = [...filterDraft.industry_groups]
  filterDraft.industry_groups = normalizeIndustrySelection(values ?? [], previousValues)
}

function clearResultsSearch(): void {
  controller.resultsQuery.search = ''
  controller.applyResultsFilters()
}

function rangeLabel(page: number, pageSize: number, pageItems: number, total: number): string {
  if (total <= 0 || pageItems <= 0) {
    return '0 of 0'
  }
  const start = (page - 1) * pageSize + 1
  const end = start + pageItems - 1
  return `${start}-${end} of ${total}`
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function metricColor(value: unknown, threshold: number): 'success' | 'warning' | 'error' | 'default' {
  const nextValue = toNumber(value)
  if (nextValue === null) {
    return 'default'
  }
  if (nextValue >= threshold) {
    return 'success'
  }
  if (nextValue >= threshold * 0.8) {
    return 'warning'
  }
  return 'error'
}

function finalStatusColor(value: unknown): 'success' | 'error' | 'default' {
  const normalized = String(value ?? '').toUpperCase()
  if (normalized === 'PASS') {
    return 'success'
  }
  if (normalized === 'FAIL') {
    return 'error'
  }
  return 'default'
}

function signedPercent(value: unknown): string {
  const nextValue = toNumber(value)
  if (nextValue === null) {
    return '-'
  }
  return `${nextValue >= 0 ? '+' : ''}${nextValue.toFixed(1)}%`
}

function percentColor(value: unknown): 'success' | 'error' | 'default' {
  const nextValue = toNumber(value)
  if (nextValue === null) {
    return 'default'
  }
  return nextValue >= 0 ? 'success' : 'error'
}

function openResultDetails(row: Record<string, unknown>): void {
  selectedResult.value = row
  detailDrawerOpen.value = true
}

function normalizeSymbol(value: unknown): string {
  const raw = String(value ?? '').trim().toUpperCase()
  if (!raw) {
    return ''
  }
  if (raw.endsWith('.NS') || raw.endsWith('.BO')) {
    return raw.slice(0, -3)
  }
  return raw
}

async function copyRowSymbol(row: Record<string, unknown>): Promise<void> {
  const symbol = normalizeSymbol(row.symbol)
  if (!symbol) {
    copyToastMessage.value = 'No symbol to copy'
    copyToastOpen.value = true
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(symbol)
    } else {
      const input = document.createElement('textarea')
      input.value = symbol
      input.setAttribute('readonly', 'true')
      input.style.position = 'fixed'
      input.style.top = '-9999px'
      input.style.left = '-9999px'
      document.body.appendChild(input)
      input.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(input)
      if (!copied) {
        throw new Error('Clipboard copy command failed')
      }
    }
    copyToastMessage.value = `Copied ${symbol}`
  } catch {
    copyToastMessage.value = 'Copy failed'
  }
  copyToastOpen.value = true
}

function getScreenerUrl(row: Record<string, unknown>): string {
  const symbol = normalizeSymbol(row.symbol)
  if (!symbol) {
    return ''
  }
  return `https://www.screener.in/company/${encodeURIComponent(symbol)}/`
}

function openScreenerForRow(row: Record<string, unknown>): void {
  const url = getScreenerUrl(row)
  if (!url) {
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function requestFilteredResultsDownload(): void {
  if (!controller.selectedRunId) {
    return
  }
  downloadConfirmOpen.value = true
}

function confirmFilteredResultsDownload(): void {
  downloadConfirmOpen.value = false
  controller.downloadFilteredResultsCsv()
}

function refreshLivePrices(): void {
  if (!controller.selectedRunId) {
    return
  }
  liveRefreshRequestedAt.value = new Date().toLocaleString()
  void controller.fetchRunResults(controller.selectedRunId, false, true)
}

function formatLocalDateTime(rawValue: string | null | undefined): string {
  const value = String(rawValue ?? '').trim()
  if (!value) {
    return ''
  }
  const hasTimeZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
  const normalized = hasTimeZone ? value : `${value}Z`
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

const selectedResultTitle = computed(() => {
  if (!selectedResult.value) {
    return 'Result Details'
  }
  return String(selectedResult.value.name || selectedResult.value.symbol || 'Result Details')
})

const effectiveResultsTotalPages = computed(() => {
  const total = Number(controller.resultsMeta.total || 0)
  const pageSize = Number(controller.resultsMeta.page_size || controller.resultsQuery.page_size || 25)
  if (total <= 0 || pageSize <= 0) {
    return 1
  }
  const derived = Math.ceil(total / pageSize)
  return Math.max(1, Number(controller.resultsMeta.total_pages || 0), derived)
})

const canGoPrevResultsPage = computed(() => Number(controller.resultsMeta.page || 1) > 1)
const canGoNextResultsPage = computed(
  () => Number(controller.resultsMeta.page || 1) < effectiveResultsTotalPages.value,
)

const livePriceUpdatedAt = computed(() => {
  for (const row of controller.runResults) {
    const rawValue = String((row as Record<string, unknown>).live_price_as_of ?? '').trim()
    if (!rawValue) {
      continue
    }

    const hasTimeZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(rawValue)
    const normalized = hasTimeZone ? rawValue : `${rawValue}Z`
    const parsed = new Date(normalized)
    if (Number.isNaN(parsed.getTime())) {
      continue
    }
    return parsed.toLocaleString('en-IN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
  }
  return ''
})

const livePriceStatusText = computed(() => {
  if (livePriceUpdatedAt.value) {
    return `Live updated: ${livePriceUpdatedAt.value}`
  }
  if (liveRefreshRequestedAt.value) {
    return `Live refresh requested: ${liveRefreshRequestedAt.value}`
  }
  return 'Live not refreshed yet'
})

const selectedRunStatusColor = computed<'info' | 'success' | 'warning' | 'error'>(() => {
  const status = String(controller.selectedRun?.status || '').toLowerCase()
  if (status === 'completed') {
    return 'success'
  }
  if (status === 'partial_completed') {
    return 'warning'
  }
  if (status === 'failed') {
    return 'error'
  }
  if (status === 'stopped') {
    return 'warning'
  }
  return 'info'
})

const selectedRunIsActive = computed(() => ACTIVE_RUN_STATUSES.has(String(controller.selectedRun?.status || '')))

const selectedRunStatusMessage = computed(() => {
  const message = String(controller.selectedRun?.status_message || '').trim()
  if (message) {
    return message
  }
  const stage = String(controller.selectedRun?.stage || controller.selectedRun?.status || '').trim()
  return stage ? `Stage: ${stage}` : 'No run status available'
})

const selectedRunCooldownText = computed(() => {
  const cooldownUntil = String(controller.selectedRun?.cooldown_until || '').trim()
  if (!cooldownUntil) {
    return ''
  }
  return formatLocalDateTime(cooldownUntil)
})

const selectedRunCooldownRemainingText = computed(() => {
  const cooldownUntil = String(controller.selectedRun?.cooldown_until || '').trim()
  if (!cooldownUntil) {
    return ''
  }

  const parsed = Date.parse(cooldownUntil)
  if (!Number.isFinite(parsed)) {
    return ''
  }

  const remainingMs = Math.max(0, parsed - cooldownNowMs.value)
  if (remainingMs <= 0) {
    return '0s'
  }

  const seconds = Math.ceil(remainingMs / 1000)
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60)
    const leftoverSeconds = seconds % 60
    return `${minutes}m ${leftoverSeconds}s`
  }
  return `${seconds}s`
})

const activeAdvancedFilters = computed(() => {
  const items: string[] = []
  if (controller.resultsQuery.final_status && controller.resultsQuery.final_status !== 'all') {
    items.push(`Status ${controller.resultsQuery.final_status.toUpperCase()}`)
  }
  if (controller.resultsQuery.market_cap_min || controller.resultsQuery.market_cap_max) {
    const min = controller.resultsQuery.market_cap_min || '-'
    const max = controller.resultsQuery.market_cap_max || '-'
    items.push(`MCap ${min} to ${max}`)
  }
  if (controller.resultsQuery.industry_group) {
    const labels = controller.resultsQuery.industry_group
      .split(',')
      .map((value) => value.trim())
      .filter((value) => value.length > 0)
    if (labels.length > 0) {
      items.push(`Industry ${labels.join(', ')}`)
    }
  }
  if (controller.resultsQuery.total_2y_growth_min || controller.resultsQuery.total_2y_growth_max) {
    const min = controller.resultsQuery.total_2y_growth_min || '-'
    const max = controller.resultsQuery.total_2y_growth_max || '-'
    items.push(`Total 2Y% ${min} to ${max}`)
  }
  if (controller.resultsQuery.ttm_vs_end_fy_min || controller.resultsQuery.ttm_vs_end_fy_max) {
    const min = controller.resultsQuery.ttm_vs_end_fy_min || '-'
    const max = controller.resultsQuery.ttm_vs_end_fy_max || '-'
    items.push(`TTM vs End FY% ${min} to ${max}`)
  }
  if (controller.resultsQuery.combined_growth_min || controller.resultsQuery.combined_growth_max) {
    const min = controller.resultsQuery.combined_growth_min || '-'
    const max = controller.resultsQuery.combined_growth_max || '-'
    items.push(`Combined% ${min} to ${max}`)
  }
  if (controller.resultsQuery.roce_min || controller.resultsQuery.roce_max) {
    const min = controller.resultsQuery.roce_min || '-'
    const max = controller.resultsQuery.roce_max || '-'
    items.push(`ROCE% ${min} to ${max}`)
  }
  if (controller.resultsQuery.away_min || controller.resultsQuery.away_max) {
    const min = controller.resultsQuery.away_min || '-'
    const max = controller.resultsQuery.away_max || '-'
    items.push(`% Away ${min} to ${max}`)
  }
  return items
})

const industryGroupOptions = computed(() => [
  { title: 'All Industries', value: INDUSTRY_ALL_VALUE },
  ...controller.resultIndustryGroups.map((group) => ({ title: group, value: group })),
])

const favoriteFilterOptions = computed(() =>
  [
    { title: 'All List (No Filter)', value: ALL_LIST_OPTION_VALUE },
    ...controller.favoriteResultsFilters.map((item) => ({
      title: item.is_default ? `★ ${item.name}` : item.name,
      value: item.filter_id,
    })),
  ],
)

const canSaveMoreFavorites = computed(
  () => controller.favoriteResultsFilters.length < controller.favoriteResultsFiltersMaxItems,
)

const hasSelectedSavedFavorite = computed(() =>
  controller.favoriteResultsFilters.some((item) => item.filter_id === controller.activeFavoriteFilterId),
)

const filterPopupSaveLabel = computed(() =>
  hasSelectedSavedFavorite.value ? 'Update Filter' : 'Save Filter',
)

const resultsTableHeight = computed(() => 'clamp(420px, calc(100vh - 430px), 760px)')

function goToPrevResultsPage(): void {
  if (!canGoPrevResultsPage.value) {
    return
  }
  controller.setResultsPage(Number(controller.resultsMeta.page || 1) - 1)
}

function goToNextResultsPage(): void {
  if (!canGoNextResultsPage.value) {
    return
  }
  controller.setResultsPage(Number(controller.resultsMeta.page || 1) + 1)
}

onMounted(() => {
  cooldownTickerHandle = window.setInterval(() => {
    cooldownNowMs.value = Date.now()
  }, 1000)
  void applyRouteRunId()
})

onBeforeUnmount(() => {
  if (cooldownTickerHandle) {
    window.clearInterval(cooldownTickerHandle)
    cooldownTickerHandle = undefined
  }
})

watch(
  () => route.params.runId,
  () => {
    runActionError.value = ''
    void applyRouteRunId()
  },
)

watch(
  () => route.query.result,
  () => {
    applyResultFilterFromRouteQuery()
  },
)
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card class="details-card">
        <v-card-title class="d-flex justify-space-between align-center card-heading">
          <div class="d-flex ga-2 align-center">
            <v-btn variant="tonal" @click="router.push('/runs')">Back To Runs</v-btn>
            <div>
              <div>Run Details</div>
              <div class="text-body-2 text-medium-emphasis">Detailed output for selected run</div>
            </div>
          </div>
          <div class="d-flex ga-2 align-center">
            <v-chip size="small" color="primary" variant="tonal">Step 3: Review Results</v-chip>
            <v-chip v-if="controller.selectedRunId" variant="tonal" size="small">{{ controller.selectedRunId.slice(0, 8) }}</v-chip>
            <v-btn
              variant="flat"
              color="primary"
              :disabled="!controller.selectedRunId"
              @click="requestFilteredResultsDownload"
            >
              Export Filtered CSV
            </v-btn>
          </div>
        </v-card-title>

        <v-card-text class="details-card-body">
          <div v-if="controller.loadingResults" class="results-loader-wrap">
            <v-progress-circular
              indeterminate
              color="primary"
              size="56"
              width="5"
            />
            <div class="text-body-2 text-medium-emphasis mt-3">Loading run results...</div>
          </div>

          <template v-else>
            <v-sheet class="list-toolbar-strip mb-3" rounded="lg">
              <div class="d-flex align-center justify-space-between ga-2 flex-wrap">
                <div class="d-flex align-center ga-2 text-body-2 text-medium-emphasis">
                  <v-icon size="18" color="primary">mdi-table-search</v-icon>
                  Refine and inspect result rows. Use search + filters, then export what you see.
                </div>
                <v-chip size="small" color="primary" variant="tonal">{{ controller.resultsMeta.total }} rows</v-chip>
              </div>
            </v-sheet>

            <v-alert v-if="!controller.selectedRunId" type="info" variant="tonal" class="mb-3">
              Select a run from Runs page to view symbol-level results and export filtered CSV.
            </v-alert>

            <v-alert
              v-if="runActionError"
              type="error"
              variant="tonal"
              density="comfortable"
              class="mb-3"
              closable
              @click:close="runActionError = ''"
            >
              {{ runActionError }}
            </v-alert>

            <v-sheet v-if="controller.selectedRun" class="run-progress-strip mb-3" rounded="lg">
              <div class="run-progress-strip-header">
                <div class="d-flex align-center ga-2 flex-wrap">
                  <v-chip size="small" :color="selectedRunStatusColor" variant="tonal">
                    {{ controller.selectedRun.status }}
                  </v-chip>
                  <v-chip size="small" variant="tonal" color="primary">
                    {{ controller.selectedRun.stage || controller.selectedRun.status }}
                  </v-chip>
                  <v-chip v-if="selectedRunCooldownText" size="small" variant="outlined" color="warning">
                    Cooldown {{ selectedRunCooldownRemainingText }} (until {{ selectedRunCooldownText }})
                  </v-chip>
                </div>
              </div>
              <div class="text-body-2 text-medium-emphasis mt-1">{{ selectedRunStatusMessage }}</div>
              <div class="run-progress-strip-metrics">
                <span>{{ controller.selectedRun.processed }} / {{ controller.selectedRun.total }} processed</span>
                <span>PASS {{ controller.selectedRun.pass_count }}</span>
                <span>FAIL {{ controller.selectedRun.fail_count }}</span>
                <span>Skipped {{ controller.selectedRun.skipped_count }}</span>
              </div>
              <v-progress-linear
                :model-value="controller.progressPct"
                :color="selectedRunIsActive ? 'primary' : selectedRunStatusColor"
                height="10"
                rounded
              />
            </v-sheet>

            <v-row v-if="controller.selectedRunId" class="mb-2">
              <v-col cols="12" class="d-flex ga-2 align-center flex-wrap">
                <v-select
                  v-model="controller.activeFavoriteFilterId"
                  :items="favoriteFilterOptions"
                  label="Favorite Filters"
                  placeholder="Select favorite"
                  clearable
                  hide-details
                  :loading="controller.favoriteResultsFiltersLoading"
                  style="min-width: 280px; max-width: 420px"
                  @update:model-value="(value) => applySelectedFavoriteFilter(String(value ?? ''))"
                />
                <v-chip size="small" variant="tonal" color="primary">
                  {{ controller.favoriteResultsFilters.length }} / {{ controller.favoriteResultsFiltersMaxItems }} saved
                </v-chip>
                <v-tooltip text="Save favorite" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-content-save-outline"
                      size="small"
                      variant="tonal"
                      color="primary"
                      :disabled="!canSaveMoreFavorites"
                      @click="openFavoriteDialog"
                    />
                  </template>
                </v-tooltip>
                <v-tooltip text="Set selected as default" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-star-outline"
                      size="small"
                      variant="tonal"
                      color="warning"
                      :disabled="!hasSelectedSavedFavorite"
                      @click="setSelectedFavoriteAsDefault"
                    />
                  </template>
                </v-tooltip>
                <v-tooltip text="Edit selected favorite" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-pencil-outline"
                      size="small"
                      variant="tonal"
                      color="primary"
                      :disabled="!hasSelectedSavedFavorite"
                      @click="openRenameFavoriteDialog"
                    />
                  </template>
                </v-tooltip>
                <v-tooltip text="Delete selected favorite" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-delete-outline"
                      size="small"
                      variant="text"
                      color="error"
                      :disabled="!hasSelectedSavedFavorite"
                      @click="requestDeleteSelectedFavoriteFilter"
                    />
                  </template>
                </v-tooltip>
              </v-col>
            </v-row>

            <v-row v-if="controller.selectedRunId" class="mb-2">
              <v-col cols="12" lg="4">
                <v-text-field
                  v-model="controller.resultsQuery.search"
                  label="Search results"
                  placeholder="Name, symbol, status, error"
                  prepend-inner-icon="mdi-magnify"
                  clear-icon="mdi-close-circle"
                  clearable
                  persistent-clear
                  @click:clear="clearResultsSearch"
                  @keyup.enter="controller.applyResultsFilters"
                />
              </v-col>
              <v-col cols="12" sm="6" lg="2">
                <v-select
                  v-model="controller.resultsQuery.final_status"
                  :items="resultStatusOptions"
                  item-title="title"
                  item-value="value"
                  label="Final status"
                  @update:model-value="controller.applyResultsFilters"
                />
              </v-col>
              <v-col cols="12" sm="6" lg="3">
                <v-select
                  v-model="controller.resultsQuery.sort_by"
                  :items="resultSortOptions"
                  item-title="title"
                  item-value="value"
                  label="Sort by"
                  @update:model-value="controller.applyResultsFilters"
                />
              </v-col>
              <v-col cols="12" lg="auto" class="results-actions-col">
                <div class="results-actions-toolbar">
                  <div class="results-actions-buttons">
                    <v-btn variant="flat" @click="controller.applyResultsFilters">Search</v-btn>
                    <v-btn variant="tonal" color="primary" prepend-icon="mdi-filter-variant" @click="openFilterDialog">
                      Filter
                    </v-btn>
                    <v-btn
                      variant="tonal"
                      color="primary"
                      prepend-icon="mdi-refresh"
                      :loading="controller.loadingResults"
                      @click="refreshLivePrices"
                    >
                      Refresh Live
                    </v-btn>
                  </div>
                  <v-chip
                    v-if="controller.selectedRunId"
                    size="small"
                    variant="outlined"
                    color="secondary"
                    class="results-live-chip"
                  >
                    {{ livePriceStatusText }}
                  </v-chip>
                </div>
              </v-col>
            </v-row>

            <div v-if="activeAdvancedFilters.length > 0" class="mb-2 d-flex ga-2 flex-wrap">
              <v-chip
                v-for="label in activeAdvancedFilters"
                :key="label"
                size="small"
                color="primary"
                variant="tonal"
              >
                {{ label }}
              </v-chip>
            </div>

            <v-data-table
              class="results-table polished-table"
              :headers="resultHeaders"
              :items="controller.runResults"
              fixed-header
              :height="resultsTableHeight"
              density="compact"
              hide-default-footer
              :items-per-page="-1"
            >
              <template #item.symbol="{ item }">
                <div class="d-flex align-center ga-1">
                  <span>{{ item.symbol || '-' }}</span>
                  <v-tooltip text="Copy symbol" location="top">
                    <template #activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-content-copy"
                        size="x-small"
                        variant="text"
                        color="secondary"
                        :disabled="!normalizeSymbol(item.symbol)"
                        @click="copyRowSymbol(item)"
                      />
                    </template>
                  </v-tooltip>
                </div>
              </template>

              <template #item.final_status="{ item }">
                <v-chip size="small" :color="finalStatusColor(item.final_status)" variant="tonal">
                  {{ item.final_status || '-' }}
                </v-chip>
              </template>

              <template #item.total_2y_growth_pct="{ item }">
                <v-chip size="small" :color="metricColor(item.total_2y_growth_pct, MIN_TOTAL_GROWTH)" variant="tonal">
                  {{ item.total_2y_growth_pct ?? '-' }}
                </v-chip>
              </template>

              <template #item.ttm_vs_end_fy_pct="{ item }">
                <v-chip size="small" :color="metricColor(item.ttm_vs_end_fy_pct, MIN_TTM_GROWTH)" variant="tonal">
                  {{ item.ttm_vs_end_fy_pct ?? '-' }}
                </v-chip>
              </template>

              <template #item.combined_growth_pct="{ item }">
                <v-chip size="small" :color="metricColor(item.combined_growth_pct, MIN_COMBINED_GROWTH)" variant="tonal">
                  {{ item.combined_growth_pct ?? '-' }}
                </v-chip>
              </template>

              <template #item.price_2y_change_pct="{ item }">
                <v-chip size="small" :color="percentColor(item.price_2y_change_pct)" variant="tonal">
                  {{ signedPercent(item.price_2y_change_pct) }}
                </v-chip>
              </template>

              <template #item.error="{ item }">
                <v-chip
                  v-if="item.error"
                  size="small"
                  color="error"
                  variant="tonal"
                  class="error-chip"
                >
                  {{ item.error }}
                </v-chip>
                <span v-else class="text-medium-emphasis">-</span>
              </template>

              <template #item.actions="{ item }">
                <div class="table-action-group">
                  <v-tooltip text="Details" location="top">
                    <template #activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-information-outline"
                        size="small"
                        variant="tonal"
                        color="primary"
                        @click="openResultDetails(item)"
                      />
                    </template>
                  </v-tooltip>

                  <v-tooltip text="Open in Screener" location="top">
                    <template #activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-open-in-new"
                        size="small"
                        variant="tonal"
                        color="primary"
                        :disabled="!getScreenerUrl(item)"
                        @click="openScreenerForRow(item)"
                      />
                    </template>
                  </v-tooltip>
                </div>
              </template>

              <template #no-data>No result rows available yet.</template>
            </v-data-table>

            <div v-if="controller.selectedRunId" class="results-footer-bar d-flex justify-space-between align-center mt-3 flex-wrap ga-3">
              <div class="text-body-2 text-medium-emphasis">
                {{ rangeLabel(controller.resultsMeta.page, controller.resultsMeta.page_size, controller.runResults.length, controller.resultsMeta.total) }}
              </div>
              <div class="d-flex align-center ga-3">
                <v-select
                  label="Rows"
                  :items="[25, 50, 100]"
                  :model-value="controller.resultsQuery.page_size"
                  style="max-width: 120px"
                  @update:model-value="onResultsPageSizeChange"
                />
                <v-btn
                  variant="tonal"
                  size="small"
                  :disabled="!canGoPrevResultsPage"
                  @click="goToPrevResultsPage"
                >
                  Prev
                </v-btn>
                <v-pagination
                  :model-value="controller.resultsMeta.page"
                  :length="effectiveResultsTotalPages"
                  :total-visible="7"
                  show-first-last-page
                  density="comfortable"
                  @update:model-value="controller.setResultsPage"
                />
                <v-btn
                  variant="tonal"
                  size="small"
                  :disabled="!canGoNextResultsPage"
                  @click="goToNextResultsPage"
                >
                  Next
                </v-btn>
                <v-chip size="small" variant="tonal" color="primary">
                  Page {{ controller.resultsMeta.page }} / {{ effectiveResultsTotalPages }}
                </v-chip>
              </div>
            </div>
          </template>
        </v-card-text>
      </v-card>

      <v-navigation-drawer
        v-model="detailDrawerOpen"
        location="right"
        temporary
        width="420"
      >
        <div class="result-drawer">
          <div class="drawer-title">{{ selectedResultTitle }}</div>
          <div class="drawer-subtitle">Expanded symbol-level diagnostic output</div>

          <v-divider class="my-3" />

          <div v-if="selectedResult" class="drawer-grid">
            <div class="drawer-row"><span>Symbol</span><strong>{{ selectedResult.symbol || '-' }}</strong></div>
            <div class="drawer-row"><span>Status</span><strong>{{ selectedResult.final_status || '-' }}</strong></div>
            <div class="drawer-row"><span>Industry</span><strong>{{ selectedResult.industry_group || '-' }}</strong></div>
            <div class="drawer-row"><span>Mark.Cap</span><strong>{{ selectedResult.market_cap_cr || '-' }}</strong></div>
            <div class="drawer-row"><span>Base Revenue</span><strong>{{ selectedResult.base_rev_cr || '-' }}</strong></div>
            <div class="drawer-row"><span>End Revenue</span><strong>{{ selectedResult.end_rev_cr || '-' }}</strong></div>
            <div class="drawer-row"><span>Total 2Y Growth</span><strong>{{ selectedResult.total_2y_growth_pct || '-' }}</strong></div>
            <div class="drawer-row"><span>TTM Revenue</span><strong>{{ selectedResult.ttm_rev_cr || '-' }}</strong></div>
            <div class="drawer-row"><span>TTM vs End FY</span><strong>{{ selectedResult.ttm_vs_end_fy_pct || '-' }}</strong></div>
            <div class="drawer-row"><span>Combined Growth</span><strong>{{ selectedResult.combined_growth_pct || '-' }}</strong></div>
            <div class="drawer-row"><span>Live Price</span><strong>{{ selectedResult.current_price || '-' }}</strong></div>
            <div class="drawer-row"><span>Entry Price</span><strong>{{ selectedResult.price_2y_ago || '-' }}</strong></div>
            <div class="drawer-row"><span>% Away</span><strong>{{ signedPercent(selectedResult.price_2y_change_pct) }}</strong></div>
            <div class="drawer-row"><span>ROCE %</span><strong>{{ selectedResult.roce_pct || '-' }}</strong></div>
            <div class="drawer-row drawer-row-error"><span>Error</span><strong>{{ selectedResult.error || '-' }}</strong></div>
          </div>
        </div>
      </v-navigation-drawer>

      <v-dialog v-model="favoriteDialogOpen" max-width="520">
        <v-card>
          <v-card-title>Save Favorite Filter</v-card-title>
          <v-card-text>
            <v-alert
              v-if="favoriteError"
              type="error"
              variant="tonal"
              density="comfortable"
              class="mb-3"
              closable
              @click:close="favoriteError = ''"
            >
              {{ favoriteError }}
            </v-alert>
            <v-text-field
              v-model="favoriteName"
              label="Favorite Name"
              placeholder="Example: My Swing Picks"
              maxlength="60"
              counter
            />
            <v-checkbox
              v-model="favoriteSetAsDefault"
              label="Set as default for this page"
              density="compact"
              hide-details
            />
          </v-card-text>
          <v-card-actions class="justify-end">
            <v-btn variant="text" color="secondary" @click="favoriteDialogOpen = false">Cancel</v-btn>
            <v-btn
              variant="flat"
              color="primary"
              :loading="favoriteBusy"
              :disabled="!favoriteName.trim()"
              @click="saveFavoriteFilter"
            >
              Save
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog v-model="favoriteRenameDialogOpen" max-width="520">
        <v-card>
          <v-card-title>Edit Favorite Filter</v-card-title>
          <v-card-text>
            <v-alert
              v-if="favoriteRenameError"
              type="error"
              variant="tonal"
              density="comfortable"
              class="mb-3"
              closable
              @click:close="favoriteRenameError = ''"
            >
              {{ favoriteRenameError }}
            </v-alert>
            <v-text-field
              v-model="favoriteRenameName"
              label="Favorite Name"
              maxlength="60"
              counter
            />
            <v-checkbox
              v-model="favoriteRenameReplaceQuery"
              label="Replace saved filter with current search and filter values"
              density="compact"
              hide-details
              class="mb-2"
            />
            <v-checkbox
              v-model="favoriteRenameSetAsDefault"
              label="Set as default for this page"
              density="compact"
              hide-details
            />
          </v-card-text>
          <v-card-actions class="justify-end">
            <v-btn variant="text" color="secondary" @click="favoriteRenameDialogOpen = false">Cancel</v-btn>
            <v-btn
              variant="flat"
              color="primary"
              :loading="favoriteRenameBusy"
              :disabled="!favoriteRenameName.trim()"
              @click="renameSelectedFavoriteFilter"
            >
              Save
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog v-model="deleteFavoriteConfirmOpen" max-width="500">
        <v-card>
          <v-card-title>Delete Favorite Filter</v-card-title>
          <v-card-text>
            This will permanently remove the selected favorite filter.
            Are you sure you want to delete it?
          </v-card-text>
          <v-card-actions class="justify-end">
            <v-btn
              variant="text"
              color="secondary"
              :disabled="favoriteRenameBusy"
              @click="deleteFavoriteConfirmOpen = false"
            >
              Cancel
            </v-btn>
            <v-btn
              variant="flat"
              color="error"
              :loading="favoriteRenameBusy"
              @click="deleteSelectedFavoriteFilter"
            >
              Yes, Delete
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog v-model="filterDialogOpen" max-width="760">
        <v-card>
          <v-card-title>Filter Results</v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="6">
                <v-select
                  v-model="filterDraft.final_status"
                  :items="resultStatusOptions"
                  item-title="title"
                  item-value="value"
                  label="Final Status"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-autocomplete
                  v-model="filterDraft.industry_groups"
                  :items="industryGroupOptions"
                  item-title="title"
                  item-value="value"
                  label="Industry Group"
                  placeholder="Select one or more industries"
                  clearable
                  multiple
                  chips
                  @update:model-value="onIndustryGroupsSelectionChange"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.market_cap_min"
                  label="Market Cap Min"
                  placeholder="1000"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.market_cap_max"
                  label="Market Cap Max"
                  placeholder="10000"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.total_2y_growth_min"
                  label="Total 2Y % Min"
                  placeholder="32"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.total_2y_growth_max"
                  label="Total 2Y % Max"
                  placeholder="80"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.ttm_vs_end_fy_min"
                  label="TTM vs End FY % Min"
                  placeholder="5"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.ttm_vs_end_fy_max"
                  label="TTM vs End FY % Max"
                  placeholder="50"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.combined_growth_min"
                  label="Combined % Min"
                  placeholder="30"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.combined_growth_max"
                  label="Combined % Max"
                  placeholder="80"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.roce_min"
                  label="ROCE % Min"
                  placeholder="10"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.roce_max"
                  label="ROCE % Max"
                  placeholder="60"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.away_min"
                  label="% Away Min"
                  placeholder="-10"
                  type="number"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filterDraft.away_max"
                  label="% Away Max (<=)"
                  placeholder="5"
                  type="number"
                  clearable
                />
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions class="justify-space-between px-4 pb-4">
            <div class="d-flex ga-2">
              <v-btn variant="text" color="secondary" @click="clearAdvancedFilters">Clear</v-btn>
              <v-btn variant="text" color="secondary" @click="filterDialogOpen = false">Cancel</v-btn>
            </div>
            <div class="d-flex ga-2">
              <v-btn
                variant="tonal"
                color="primary"
                :disabled="favoriteBusy || (!canSaveMoreFavorites && !hasSelectedSavedFavorite)"
                @click="saveOrCreateFavoriteFromFilterPopup"
              >
                {{ filterPopupSaveLabel }}
              </v-btn>
              <v-btn variant="flat" color="primary" @click="applyAdvancedFilters">Apply</v-btn>
            </div>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-dialog v-model="downloadConfirmOpen" max-width="460">
        <v-card>
          <v-card-title>Download Filtered Results CSV</v-card-title>
          <v-card-text>Are you sure you want to download the filtered results CSV?</v-card-text>
          <v-card-actions class="justify-end">
            <v-btn variant="text" color="secondary" @click="downloadConfirmOpen = false">Cancel</v-btn>
            <v-btn variant="flat" color="primary" @click="confirmFilteredResultsDownload">Yes, Download</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-snackbar
        v-model="copyToastOpen"
        timeout="1500"
        location="bottom right"
        color="secondary"
        variant="tonal"
      >
        {{ copyToastMessage }}
      </v-snackbar>
    </v-col>
  </v-row>
</template>

<style scoped>
.details-card {
  min-height: calc(100vh - 220px);
}

.details-card-body {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 320px);
}

.results-footer-bar {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
}

.results-loader-wrap {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.run-progress-strip {
  padding: 12px;
  border: 1px solid #e2e5ea;
  background: #f7f8fa;
}

.run-progress-strip-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.run-progress-strip-metrics {
  margin: 8px 0;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.875rem;
  color: rgba(15, 23, 42, 0.78);
}

.results-actions-col :deep(.v-btn) {
  min-height: 36px;
}

.results-actions-col :deep(.v-chip) {
  min-height: 32px;
}

.results-actions-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  min-height: 56px;
}

.results-actions-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}

@media (min-width: 1280px) {
  .results-actions-toolbar,
  .results-actions-buttons {
    flex-wrap: nowrap;
  }
}

@media (max-width: 960px) {
  .details-card {
    min-height: auto;
  }

  .details-card-body {
    min-height: auto;
  }

  .results-footer-bar {
    margin-top: 12px;
  }

  .results-actions-toolbar,
  .results-actions-buttons {
    justify-content: flex-start;
  }
}
</style>
