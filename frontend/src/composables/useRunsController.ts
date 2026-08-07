import { computed, ref } from 'vue'

export type RunSummary = {
  run_id: string
  status: string
  stage?: string
  status_message?: string
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  stopped_at: string | null
  cooldown_until?: string | null
  input_universe: string
  output_mode: string
  refresh: boolean
  processed: number
  total: number
  pass_count: number
  fail_count: number
  skipped_count: number
  retry_count?: number
}

const ACTIVE_RUN_STATUSES = new Set(['queued', 'preparing', 'running', 'cooling_down'])

export type UploadValidationResponse = {
  upload_id: string | null
  filename: string
  valid: boolean
  allowed_headers: string[]
  detected_headers: string[]
  missing_headers: string[]
  unexpected_headers: string[]
  total_rows: number
  accepted_rows: number
  rejected_rows: number
  errors: string[]
  preview_rows: Record<string, string>[]
}

type PagedResponse<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

type PaginationMeta = {
  total: number
  page: number
  page_size: number
  total_pages: number
}

type RunsQuery = {
  search: string
  status: string
  created_from: string
  created_to: string
  sort_by: string
  sort_order: 'asc' | 'desc'
  page: number
  page_size: number
}

type ResultsQuery = {
  search: string
  final_status: string
  live_price: boolean
  market_cap_min: string
  market_cap_max: string
  industry_group: string
  total_2y_growth_min: string
  total_2y_growth_max: string
  ttm_vs_end_fy_min: string
  ttm_vs_end_fy_max: string
  combined_growth_min: string
  combined_growth_max: string
  roce_min: string
  roce_max: string
  away_min: string
  away_max: string
  sort_by: string
  sort_order: 'asc' | 'desc'
  page: number
  page_size: number
}

export type FavoriteResultsFilterQuery = {
  search: string
  final_status: string
  market_cap_min: string
  market_cap_max: string
  industry_group: string
  total_2y_growth_min: string
  total_2y_growth_max: string
  ttm_vs_end_fy_min: string
  ttm_vs_end_fy_max: string
  combined_growth_min: string
  combined_growth_max: string
  roce_min: string
  roce_max: string
  away_min: string
  away_max: string
  sort_by: string
  sort_order: 'asc' | 'desc'
  page_size: number
}

export type FavoriteResultsFilter = {
  filter_id: string
  name: string
  query: FavoriteResultsFilterQuery
  is_default: boolean
  created_at: string
  updated_at: string
}

type FavoriteResultsFilterListResponse = {
  items: FavoriteResultsFilter[]
  max_items: number
}

const API_BASE_URL =
  normalizeLoopbackApiBase(
    import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
  )

function normalizeLoopbackApiBase(rawBase: string): string {
  try {
    const parsed = new URL(rawBase, window.location.origin)
    const frontendHost = window.location.hostname
    if (
      (frontendHost === 'localhost' && parsed.hostname === '127.0.0.1') ||
      (frontendHost === '127.0.0.1' && parsed.hostname === 'localhost')
    ) {
      parsed.hostname = frontendHost
    }
    return parsed.origin
  } catch {
    return rawBase
  }
}

const runs = ref<RunSummary[]>([])
const loading = ref(false)
const submitting = ref(false)
const uploading = ref(false)
const errorMessage = ref('')
const healthStatus = ref('checking')
const selectedFile = ref<File | null>(null)
const uploadResult = ref<UploadValidationResponse | null>(null)
const uploadError = ref('')
const selectedRunId = ref('')
const runResults = ref<Record<string, unknown>[]>([])
const resultIndustryGroups = ref<string[]>([])
const loadingResults = ref(false)
const runsMeta = ref<PaginationMeta>({
  total: 0,
  page: 1,
  page_size: 10,
  total_pages: 1,
})
const resultsMeta = ref<PaginationMeta>({
  total: 0,
  page: 1,
  page_size: 25,
  total_pages: 1,
})
const favoriteResultsFilters = ref<FavoriteResultsFilter[]>([])
const favoriteResultsFiltersLoading = ref(false)
const favoriteResultsFiltersMaxItems = ref(5)
const activeFavoriteFilterId = ref('')

const runsQuery = ref<RunsQuery>({
  search: '',
  status: 'all',
  created_from: '',
  created_to: '',
  sort_by: 'created_at',
  sort_order: 'desc',
  page: 1,
  page_size: 10,
})

const resultsQuery = ref<ResultsQuery>({
  search: '',
  final_status: 'all',
  live_price: false,
  market_cap_min: '',
  market_cap_max: '',
  industry_group: '',
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
  sort_by: 'name',
  sort_order: 'asc',
  page: 1,
  page_size: 25,
})

const selectedRunCache = ref<RunSummary | null>(null)

const form = ref({
  input_universe: 'nifty-500-v2',
  output_mode: 'csv',
  refresh: true,
})

const passTotal = computed(() => runs.value.reduce((sum, run) => sum + run.pass_count, 0))
const failTotal = computed(() => runs.value.reduce((sum, run) => sum + run.fail_count, 0))
const skipTotal = computed(() => runs.value.reduce((sum, run) => sum + run.skipped_count, 0))
const selectedRun = computed(() => {
  const runFromCurrentPage = runs.value.find((run) => run.run_id === selectedRunId.value) ?? null
  if (runFromCurrentPage) {
    return runFromCurrentPage
  }
  if (selectedRunCache.value?.run_id === selectedRunId.value) {
    return selectedRunCache.value
  }
  return null
})
const progressPct = computed(() => {
  const run = selectedRun.value
  if (!run || run.total <= 0) {
    return 0
  }
  return Math.min(100, Math.round((run.processed / run.total) * 100))
})
const canDownloadCsv = computed(() => {
  const status = String(selectedRun.value?.status || '')
  return status === 'completed' || status === 'partial_completed'
})
const activeRun = computed(() => runs.value.find((run) => ACTIVE_RUN_STATUSES.has(run.status)) ?? null)
const hasActiveRun = computed(() => !!activeRun.value)

let pollHandle: number | undefined
let initialized = false
const industryGroupsCache = new Map<string, string[]>()

async function checkHealth(): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      credentials: 'include',
    })
    healthStatus.value = response.ok ? 'online' : 'offline'
  } catch {
    healthStatus.value = 'offline'
  }
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    credentials: 'include',
  })
}

function _buildQueryString(payload: Record<string, string | number | boolean>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(payload)) {
    params.set(key, String(value))
  }
  return params.toString()
}

function _toFavoriteResultsFilterQuery(): FavoriteResultsFilterQuery {
  return {
    search: resultsQuery.value.search,
    final_status: resultsQuery.value.final_status,
    market_cap_min: resultsQuery.value.market_cap_min,
    market_cap_max: resultsQuery.value.market_cap_max,
    industry_group: resultsQuery.value.industry_group,
    total_2y_growth_min: resultsQuery.value.total_2y_growth_min,
    total_2y_growth_max: resultsQuery.value.total_2y_growth_max,
    ttm_vs_end_fy_min: resultsQuery.value.ttm_vs_end_fy_min,
    ttm_vs_end_fy_max: resultsQuery.value.ttm_vs_end_fy_max,
    combined_growth_min: resultsQuery.value.combined_growth_min,
    combined_growth_max: resultsQuery.value.combined_growth_max,
    roce_min: resultsQuery.value.roce_min,
    roce_max: resultsQuery.value.roce_max,
    away_min: resultsQuery.value.away_min,
    away_max: resultsQuery.value.away_max,
    sort_by: resultsQuery.value.sort_by,
    sort_order: resultsQuery.value.sort_order,
    page_size: resultsQuery.value.page_size,
  }
}

function _applyFavoriteResultsFilterQuery(query: FavoriteResultsFilterQuery): void {
  resultsQuery.value.search = String(query.search ?? '').trim()
  resultsQuery.value.final_status = String(query.final_status ?? 'all').trim() || 'all'
  resultsQuery.value.market_cap_min = String(query.market_cap_min ?? '').trim()
  resultsQuery.value.market_cap_max = String(query.market_cap_max ?? '').trim()
  resultsQuery.value.industry_group = String(query.industry_group ?? '').trim()
  resultsQuery.value.total_2y_growth_min = String(query.total_2y_growth_min ?? '').trim()
  resultsQuery.value.total_2y_growth_max = String(query.total_2y_growth_max ?? '').trim()
  resultsQuery.value.ttm_vs_end_fy_min = String(query.ttm_vs_end_fy_min ?? '').trim()
  resultsQuery.value.ttm_vs_end_fy_max = String(query.ttm_vs_end_fy_max ?? '').trim()
  resultsQuery.value.combined_growth_min = String(query.combined_growth_min ?? '').trim()
  resultsQuery.value.combined_growth_max = String(query.combined_growth_max ?? '').trim()
  resultsQuery.value.roce_min = String(query.roce_min ?? '').trim()
  resultsQuery.value.roce_max = String(query.roce_max ?? '').trim()
  resultsQuery.value.away_min = String(query.away_min ?? '').trim()
  resultsQuery.value.away_max = String(query.away_max ?? '').trim()
  resultsQuery.value.sort_by = String(query.sort_by ?? 'name').trim() || 'name'
  resultsQuery.value.sort_order = query.sort_order === 'desc' ? 'desc' : 'asc'
  resultsQuery.value.page_size = Math.max(1, Number(query.page_size ?? 25))
  resultsQuery.value.page = 1
}

async function fetchRuns(resetPage = false): Promise<void> {
  if (resetPage) {
    runsQuery.value.page = 1
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch(
      `${API_BASE_URL}/api/runs?${_buildQueryString({
        search: runsQuery.value.search,
        status: runsQuery.value.status,
        created_from: runsQuery.value.created_from,
        created_to: runsQuery.value.created_to,
        sort_by: runsQuery.value.sort_by,
        sort_order: runsQuery.value.sort_order,
        page: runsQuery.value.page,
        page_size: runsQuery.value.page_size,
      })}`,
    )
    if (!response.ok) {
      throw new Error('Failed to load runs')
    }

    const data = (await response.json()) as PagedResponse<RunSummary> | RunSummary[]
    if (Array.isArray(data)) {
      runs.value = data
      runsMeta.value = {
        total: data.length,
        page: 1,
        page_size: data.length || 1,
        total_pages: 1,
      }
    } else {
      runs.value = data.items
      runsMeta.value = {
        total: data.total,
        page: data.page,
        page_size: data.page_size,
        total_pages: data.total_pages,
      }
    }

    if (!selectedRunId.value && runs.value.length > 0) {
      selectedRunId.value = runs.value[0].run_id
      selectedRunCache.value = runs.value[0]
    }

    if (selectedRunId.value) {
      const selectedFromList = runs.value.find((run) => run.run_id === selectedRunId.value) ?? null
      if (selectedFromList) {
        selectedRunCache.value = selectedFromList
      }
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unexpected error while loading runs'
  } finally {
    loading.value = false
  }
}

async function fetchRunResults(runId: string, resetPage = false, livePriceOverride?: boolean): Promise<void> {
  if (resetPage) {
    resultsQuery.value.page = 1
  }

  loadingResults.value = true
  try {
    const response = await apiFetch(
      `${API_BASE_URL}/api/runs/${runId}/results?${_buildQueryString({
        search: resultsQuery.value.search,
        final_status: resultsQuery.value.final_status,
        live_price: livePriceOverride ?? resultsQuery.value.live_price,
        market_cap_min: resultsQuery.value.market_cap_min,
        market_cap_max: resultsQuery.value.market_cap_max,
        industry_group: resultsQuery.value.industry_group,
        total_2y_growth_min: resultsQuery.value.total_2y_growth_min,
        total_2y_growth_max: resultsQuery.value.total_2y_growth_max,
        ttm_vs_end_fy_min: resultsQuery.value.ttm_vs_end_fy_min,
        ttm_vs_end_fy_max: resultsQuery.value.ttm_vs_end_fy_max,
        combined_growth_min: resultsQuery.value.combined_growth_min,
        combined_growth_max: resultsQuery.value.combined_growth_max,
        roce_min: resultsQuery.value.roce_min,
        roce_max: resultsQuery.value.roce_max,
        away_min: resultsQuery.value.away_min,
        away_max: resultsQuery.value.away_max,
        sort_by: resultsQuery.value.sort_by,
        sort_order: resultsQuery.value.sort_order,
        page: resultsQuery.value.page,
        page_size: resultsQuery.value.page_size,
      })}`,
    )
    if (!response.ok) {
      throw new Error('Failed to load run results')
    }

    const data = (await response.json()) as
      | PagedResponse<Record<string, unknown>>
      | Record<string, unknown>[]

    if (Array.isArray(data)) {
      runResults.value = data
      resultsMeta.value = {
        total: data.length,
        page: 1,
        page_size: data.length || 1,
        total_pages: 1,
      }
    } else {
      runResults.value = data.items
      resultsMeta.value = {
        total: data.total,
        page: data.page,
        page_size: data.page_size,
        total_pages: data.total_pages,
      }
    }

    if (industryGroupsCache.has(runId)) {
      resultIndustryGroups.value = industryGroupsCache.get(runId) ?? []
    } else {
      await fetchRunIndustryGroups(runId)
    }
  } catch {
    runResults.value = []
    resultIndustryGroups.value = []
    resultsMeta.value = {
      total: 0,
      page: 1,
      page_size: resultsQuery.value.page_size,
      total_pages: 1,
    }
  } finally {
    loadingResults.value = false
  }
}

async function fetchRunIndustryGroups(runId: string): Promise<void> {
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/runs/${runId}/industry-groups`)
    if (!response.ok) {
      throw new Error('Failed to load industry groups')
    }
    const data = (await response.json()) as string[]
    industryGroupsCache.set(runId, data)
    resultIndustryGroups.value = data
  } catch {
    resultIndustryGroups.value = []
  }
}

async function _throwApiError(response: Response, fallbackMessage: string): Promise<never> {
  const payload = (await response.json().catch(() => null)) as { detail?: string; message?: string } | null
  throw new Error(payload?.detail || payload?.message || fallbackMessage)
}

async function startRun(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    if (!response.ok) {
      await _throwApiError(response, 'Failed to create run')
    }
    const created = (await response.json()) as RunSummary
    selectedRunId.value = created.run_id
    selectedRunCache.value = created
    await fetchRuns(true)
    await fetchRunResults(created.run_id, true)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unexpected error while creating run'
  } finally {
    submitting.value = false
  }
}

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
  uploadError.value = ''
  uploadResult.value = null
}

function clearUploadWorkflowState(): void {
  uploadError.value = ''
  uploadResult.value = null
}

async function validateUpload(): Promise<void> {
  if (!selectedFile.value) {
    uploadError.value = 'Please choose a CSV file first.'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadResult.value = null

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const response = await apiFetch(`${API_BASE_URL}/api/uploads/validate`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error('File validation failed')
    }

    uploadResult.value = (await response.json()) as UploadValidationResponse
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : 'Unexpected upload error'
  } finally {
    uploading.value = false
  }
}

async function startRunFromUpload(): Promise<void> {
  if (!uploadResult.value?.valid || !uploadResult.value.upload_id) {
    uploadError.value = 'Validate a correct CSV file before starting a run.'
    return
  }

  submitting.value = true
  uploadError.value = ''
  try {
    const response = await apiFetch(
      `${API_BASE_URL}/api/runs/from-upload/${uploadResult.value.upload_id}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_mode: form.value.output_mode,
          refresh: form.value.refresh,
        }),
      },
    )
    if (!response.ok) {
      await _throwApiError(response, 'Failed to create run from uploaded file')
    }
    const created = (await response.json()) as RunSummary
    selectedRunId.value = created.run_id
    selectedRunCache.value = created
    await fetchRuns(true)
    await fetchRunResults(created.run_id, true)
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : 'Unexpected error while creating run'
  } finally {
    submitting.value = false
  }
}

async function startValidatedWorkflowRun(): Promise<void> {
  if (!uploadResult.value?.valid || !uploadResult.value.upload_id) {
    uploadError.value = 'Validate a correct CSV file before starting workflow run.'
    return
  }

  submitting.value = true
  uploadError.value = ''
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/workflows/upload-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_id: uploadResult.value.upload_id,
        output_mode: form.value.output_mode,
        refresh: form.value.refresh,
        confirm_run: true,
      }),
    })
    if (!response.ok) {
      await _throwApiError(response, 'Failed to start workflow run from validated upload')
    }
    const created = (await response.json()) as RunSummary
    selectedRunId.value = created.run_id
    selectedRunCache.value = created
    await fetchRuns(true)
    await fetchRunResults(created.run_id, true)
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : 'Unexpected workflow execution error'
  } finally {
    submitting.value = false
  }
}

async function stopRun(runId: string): Promise<void> {
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/runs/${runId}/stop`, {
      method: 'POST',
    })
    if (!response.ok) {
      throw new Error('Failed to stop run')
    }
    await fetchRuns()
    if (selectedRunId.value === runId) {
      await fetchRunResults(runId)
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unexpected error while stopping run'
  }
}

function setSelectedRun(runId: string, options?: { fetch?: boolean }): void {
  selectedRunId.value = runId
  resultsQuery.value.page = 1
  const selectedFromList = runs.value.find((run) => run.run_id === runId) ?? null
  if (selectedFromList) {
    selectedRunCache.value = selectedFromList
  }
  if (options?.fetch !== false) {
    void fetchRunResults(runId)
  }
}

async function fetchFavoriteResultsFilters(): Promise<void> {
  favoriteResultsFiltersLoading.value = true
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/user/result-filters`)
    if (!response.ok) {
      throw new Error('Failed to load favorite filters')
    }

    const data = (await response.json()) as FavoriteResultsFilterListResponse
    favoriteResultsFilters.value = Array.isArray(data.items) ? data.items : []
    favoriteResultsFiltersMaxItems.value = Math.max(1, Number(data.max_items ?? 5))

    const defaultFilter = favoriteResultsFilters.value.find((item) => item.is_default) ?? null
    if (defaultFilter) {
      activeFavoriteFilterId.value = defaultFilter.filter_id
    } else if (favoriteResultsFilters.value.length > 0) {
      activeFavoriteFilterId.value = favoriteResultsFilters.value[0].filter_id
    } else {
      activeFavoriteFilterId.value = ''
    }
  } finally {
    favoriteResultsFiltersLoading.value = false
  }
}

async function saveFavoriteResultsFilter(name: string, isDefault = false): Promise<void> {
  return saveFavoriteResultsFilterWithQuery(name, isDefault)
}

async function saveFavoriteResultsFilterWithQuery(
  name: string,
  isDefault = false,
  queryOverride?: FavoriteResultsFilterQuery,
): Promise<void> {
  const trimmedName = name.trim()
  if (!trimmedName) {
    throw new Error('Favorite name is required')
  }

  const response = await apiFetch(`${API_BASE_URL}/api/user/result-filters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: trimmedName,
      query: queryOverride ?? _toFavoriteResultsFilterQuery(),
      is_default: isDefault,
    }),
  })
  if (!response.ok) {
    await _throwApiError(response, 'Failed to save favorite filter')
  }

  const saved = (await response.json()) as FavoriteResultsFilter
  await fetchFavoriteResultsFilters()
  activeFavoriteFilterId.value = saved.filter_id
}

async function updateFavoriteResultsFilter(
  filterId: string,
  name: string,
  isDefault: boolean,
  queryOverride?: FavoriteResultsFilterQuery,
): Promise<void> {
  const trimmedName = name.trim()
  if (!trimmedName) {
    throw new Error('Favorite name is required')
  }

  const response = await apiFetch(`${API_BASE_URL}/api/user/result-filters/${encodeURIComponent(filterId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: trimmedName,
      query: queryOverride ?? _toFavoriteResultsFilterQuery(),
      is_default: isDefault,
    }),
  })
  if (!response.ok) {
    await _throwApiError(response, 'Failed to update favorite filter')
  }

  await fetchFavoriteResultsFilters()
  activeFavoriteFilterId.value = filterId
}

async function deleteFavoriteResultsFilter(filterId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/api/user/result-filters/${encodeURIComponent(filterId)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await _throwApiError(response, 'Failed to delete favorite filter')
  }
  await fetchFavoriteResultsFilters()
}

async function applyFavoriteResultsFilter(filterId: string): Promise<void> {
  const target = favoriteResultsFilters.value.find((item) => item.filter_id === filterId)
  if (!target) {
    return
  }
  activeFavoriteFilterId.value = target.filter_id
  _applyFavoriteResultsFilterQuery(target.query)
  if (selectedRunId.value) {
    await fetchRunResults(selectedRunId.value, true)
  }
}

async function preloadResultsWithFavorite(runId: string): Promise<void> {
  await fetchFavoriteResultsFilters()
  const defaultFilter = favoriteResultsFilters.value.find((item) => item.is_default) ?? null
  if (defaultFilter) {
    _applyFavoriteResultsFilterQuery(defaultFilter.query)
    activeFavoriteFilterId.value = defaultFilter.filter_id
  }
  await fetchRunResults(runId, true)
}

function applyRunsFilters(): void {
  void fetchRuns(true)
}

function setRunsPage(page: number): void {
  runsQuery.value.page = Math.max(1, page)
  void fetchRuns()
}

function setRunsPageSize(pageSize: number): void {
  runsQuery.value.page_size = Math.max(1, pageSize)
  runsQuery.value.page = 1
  void fetchRuns()
}

function toggleRunsSortOrder(): void {
  runsQuery.value.sort_order = runsQuery.value.sort_order === 'asc' ? 'desc' : 'asc'
  runsQuery.value.page = 1
  void fetchRuns()
}

function applyResultsFilters(): void {
  if (!selectedRunId.value) {
    return
  }
  void fetchRunResults(selectedRunId.value, true)
}

function setResultsPage(page: number): void {
  if (!selectedRunId.value) {
    return
  }
  resultsQuery.value.page = Math.max(1, page)
  void fetchRunResults(selectedRunId.value)
}

function setResultsPageSize(pageSize: number): void {
  if (!selectedRunId.value) {
    return
  }
  resultsQuery.value.page_size = Math.max(1, pageSize)
  resultsQuery.value.page = 1
  void fetchRunResults(selectedRunId.value)
}

function toggleResultsSortOrder(): void {
  if (!selectedRunId.value) {
    return
  }
  resultsQuery.value.sort_order = resultsQuery.value.sort_order === 'asc' ? 'desc' : 'asc'
  resultsQuery.value.page = 1
  void fetchRunResults(selectedRunId.value)
}

function downloadSelectedRunCsv(): void {
  if (!selectedRunId.value || !canDownloadCsv.value) {
    return
  }
  window.open(`${API_BASE_URL}/api/runs/${selectedRunId.value}/download.csv`, '_blank')
}

function downloadFilteredRunsCsv(): void {
  const query = _buildQueryString({
    search: runsQuery.value.search,
    status: runsQuery.value.status,
    created_from: runsQuery.value.created_from,
    created_to: runsQuery.value.created_to,
    sort_by: runsQuery.value.sort_by,
    sort_order: runsQuery.value.sort_order,
  })
  window.open(`${API_BASE_URL}/api/runs/export.csv?${query}`, '_blank')
}

function downloadFilteredResultsCsv(): void {
  if (!selectedRunId.value) {
    return
  }
  const query = _buildQueryString({
    search: resultsQuery.value.search,
    final_status: resultsQuery.value.final_status,
    live_price: resultsQuery.value.live_price,
    market_cap_min: resultsQuery.value.market_cap_min,
    market_cap_max: resultsQuery.value.market_cap_max,
    industry_group: resultsQuery.value.industry_group,
    total_2y_growth_min: resultsQuery.value.total_2y_growth_min,
    total_2y_growth_max: resultsQuery.value.total_2y_growth_max,
    ttm_vs_end_fy_min: resultsQuery.value.ttm_vs_end_fy_min,
    ttm_vs_end_fy_max: resultsQuery.value.ttm_vs_end_fy_max,
    combined_growth_min: resultsQuery.value.combined_growth_min,
    combined_growth_max: resultsQuery.value.combined_growth_max,
    roce_min: resultsQuery.value.roce_min,
    roce_max: resultsQuery.value.roce_max,
    away_min: resultsQuery.value.away_min,
    away_max: resultsQuery.value.away_max,
    sort_by: resultsQuery.value.sort_by,
    sort_order: resultsQuery.value.sort_order,
  })
  window.open(`${API_BASE_URL}/api/runs/${selectedRunId.value}/results/export.csv?${query}`, '_blank')
}

function startPolling(): void {
  if (pollHandle) {
    return
  }
  pollHandle = window.setInterval(async () => {
    const activeExists = runs.value.some((run) => ACTIVE_RUN_STATUSES.has(run.status))
    if (!activeExists) {
      return
    }

    await fetchRuns()
    if (selectedRunId.value) {
      await fetchRunResults(selectedRunId.value)
    }
  }, 4000)
}

function stopPolling(): void {
  if (pollHandle) {
    window.clearInterval(pollHandle)
    pollHandle = undefined
  }
}

async function initialize(): Promise<void> {
  if (initialized) {
    return
  }
  initialized = true
  await Promise.all([checkHealth(), fetchRuns()])
  if (selectedRunId.value) {
    await fetchRunResults(selectedRunId.value)
  }
  startPolling()
}

export function useRunsController() {
  return {
    API_BASE_URL,
    runs,
    loading,
    submitting,
    uploading,
    errorMessage,
    healthStatus,
    selectedFile,
    uploadResult,
    uploadError,
    selectedRunId,
    runResults,
    resultIndustryGroups,
    loadingResults,
    runsMeta,
    resultsMeta,
    runsQuery,
    resultsQuery,
    favoriteResultsFilters,
    favoriteResultsFiltersLoading,
    favoriteResultsFiltersMaxItems,
    activeFavoriteFilterId,
    form,
    passTotal,
    failTotal,
    skipTotal,
    selectedRun,
    progressPct,
    canDownloadCsv,
    activeRun,
    hasActiveRun,
    initialize,
    startPolling,
    stopPolling,
    checkHealth,
    fetchRuns,
    fetchRunResults,
    fetchRunIndustryGroups,
    fetchFavoriteResultsFilters,
    saveFavoriteResultsFilter,
    saveFavoriteResultsFilterWithQuery,
    updateFavoriteResultsFilter,
    deleteFavoriteResultsFilter,
    applyFavoriteResultsFilter,
    preloadResultsWithFavorite,
    applyRunsFilters,
    setRunsPage,
    setRunsPageSize,
    toggleRunsSortOrder,
    applyResultsFilters,
    setResultsPage,
    setResultsPageSize,
    toggleResultsSortOrder,
    startRun,
    onFileChange,
    clearUploadWorkflowState,
    validateUpload,
    startRunFromUpload,
    startValidatedWorkflowRun,
    stopRun,
    setSelectedRun,
    downloadSelectedRunCsv,
    downloadFilteredRunsCsv,
    downloadFilteredResultsCsv,
  }
}
