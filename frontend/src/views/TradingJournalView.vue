<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

import {
  createTradingJournalEntry,
  deleteTradingJournalEntry,
  fetchLivePriceQuote,
  fetchTradingJournalEntries,
  journalExportUrl,
  type LivePriceQuote,
  updateTradingJournalEntry,
  type TradingJournalEntry,
  type TradingJournalEntryUpsertRequest,
  type TradingJournalLotUpsertRequest,
  type TradingJournalListQuery,
} from '../services/tradingJournal'

const tableHeaders = [
  { title: 'Date', key: 'trade_date' },
  { title: 'Open/Close', key: 'session' },
  { title: 'Script', key: 'script' },
  { title: 'Trade Strategy', key: 'trade_strategy' },
  { title: 'Time Period', key: 'time_period' },
  { title: 'Fills', key: 'lots' },
  { title: 'Exit Qty', key: 'exit_quantity' },
  { title: 'Current Price', key: 'current_price' },
  { title: 'Buy/Sell', key: 'side' },
  { title: 'Quantity', key: 'quantity' },
  { title: 'Entry Price', key: 'entry_price' },
  { title: 'Entry Value', key: 'entry_value' },
  { title: 'SquareOff Date', key: 'squareoff_date' },
  { title: 'Exit Price', key: 'exit_price' },
  { title: 'Profit/Loss', key: 'pnl' },
  { title: '% Gain/Loss', key: 'gain_loss_pct' },
  { title: 'SL', key: 'sl' },
  { title: 'SL %', key: 'sl_pct' },
  { title: 'TP', key: 'tp' },
  { title: 'Origination Logic', key: 'origination_logic' },
  { title: 'Comment', key: 'comment' },
  { title: 'Karma', key: 'karma' },
  { title: 'Actions', key: 'actions', sortable: false },
]

const rows = ref<TradingJournalEntry[]>([])
const loading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const editorOpen = ref(false)
const deleteConfirmOpen = ref(false)
const deleting = ref(false)
const selectedEntry = ref<TradingJournalEntry | null>(null)
const liveQuote = ref<LivePriceQuote | null>(null)
const livePricesRefreshing = ref(false)
let livePriceIntervalHandle: number | undefined
let livePriceDebounceHandle: number | undefined

const query = reactive<TradingJournalListQuery>({
  search: '',
  session: 'all',
  trade_strategy: 'all',
  time_period: 'all',
  sort_by: 'trade_date',
  sort_order: 'desc',
  include_live_price: true,
  refresh_live_price: false,
  page: 1,
  page_size: 15,
})

const meta = reactive({
  total: 0,
  page: 1,
  page_size: 15,
  total_pages: 1,
})

const journalSummary = computed(() => {
  const visibleRows = rows.value
  const openCount = visibleRows.filter((row) => (row.open_quantity ?? row.quantity) > 0).length
  const closedCount = visibleRows.length - openCount
  return [
    { label: 'Open', value: String(openCount), session: 'Open' as const, color: 'success' as const },
    { label: 'Closed', value: String(closedCount), session: 'Close' as const, color: 'error' as const },
  ]
})

const sessionOptions = [
  { title: 'All Sessions', value: 'all' },
  { title: 'Open', value: 'Open' },
  { title: 'Close', value: 'Close' },
]

const strategyFilterOptions = [
  { title: 'All Strategy', value: 'all' },
  { title: 'RS55', value: 'RS55' },
  { title: 'Growth-Gap', value: 'Growth-Gap' },
  { title: 'Range-Bound', value: 'Range-Bound' },
  { title: 'Other', value: 'Other' },
]

const timePeriodFilterOptions = [
  { title: 'All Time Period', value: 'all' },
  { title: 'ShortTerm', value: 'ShortTerm' },
  { title: 'LongTerm', value: 'LongTerm' },
]

const form = reactive<TradingJournalEntryUpsertRequest>({
  trade_date: '',
  session: 'Open',
  script: '',
  trade_strategy: 'RS55',
  time_period: 'ShortTerm',
  side: 'Buy',
  quantity: 1,
  entry_price: 0,
  entry_value: 0,
  exit_quantity: 0,
  squareoff_date: '',
  exit_price: 0,
  pnl: 0,
  gain_loss_pct: 0,
  sl: 0,
  sl_pct: 0,
  tp: 0,
  origination_logic: '',
  comment: '',
  karma: 5,
  lots: [],
})

const lots = reactive<TradingJournalLotUpsertRequest[]>([])
const customTradeStrategy = ref('')

const tradeStrategyOptions = [
  { title: 'RS55', value: 'RS55' },
  { title: 'Growth-Gap', value: 'Growth-Gap' },
  { title: 'Range-Bound', value: 'Range-Bound' },
  { title: 'Other', value: 'Other' },
]

const timePeriodOptions = [
  { title: 'ShortTerm', value: 'ShortTerm' },
  { title: 'LongTerm', value: 'LongTerm' },
]

function toNumber(value: unknown): number {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

function roundTo2(value: number): number {
  return Math.round(value * 100) / 100
}

function clearLivePriceTimers(): void {
  if (livePriceIntervalHandle !== undefined) {
    window.clearInterval(livePriceIntervalHandle)
    livePriceIntervalHandle = undefined
  }
  if (livePriceDebounceHandle !== undefined) {
    window.clearTimeout(livePriceDebounceHandle)
    livePriceDebounceHandle = undefined
  }
}

function isClosedSession(session: string): boolean {
  return session.trim().toLowerCase() === 'close'
}

function createLotRow(lotDate = '', quantity = 1, price = 0, note = ''): TradingJournalLotUpsertRequest {
  return {
    lot_date: lotDate,
    quantity,
    price,
    note,
  }
}

function resetLots(): void {
  lots.splice(0, lots.length, createLotRow())
}

function syncSummaryFromLots(): void {
  const validLots = lots.filter((lot) => Number(lot.quantity) > 0)
  const totalQuantity = validLots.reduce((sum, lot) => sum + Math.max(0, toNumber(lot.quantity)), 0)
  const entryValue = validLots.reduce((sum, lot) => sum + Math.max(0, toNumber(lot.quantity)) * Math.max(0, toNumber(lot.price)), 0)

  form.quantity = totalQuantity
  form.entry_value = roundTo2(entryValue)
  form.entry_price = totalQuantity > 0 ? roundTo2(entryValue / totalQuantity) : 0
}

function currentMarketPrice(): number {
  if (isClosedSession(form.session) || toNumber(form.exit_quantity) >= toNumber(form.quantity)) {
    return Math.max(0, toNumber(form.exit_price))
  }
  const exitPrice = Math.max(0, toNumber(form.exit_price))
  if (exitPrice > 0) {
    return exitPrice
  }
  return Math.max(0, toNumber(liveQuote.value?.current_price ?? 0))
}

function recomputeDerivedFields(): void {
  const quantity = Math.max(0, toNumber(form.quantity))
  const entryPrice = Math.max(0, toNumber(form.entry_price))
  const marketPrice = currentMarketPrice()
  const stopLoss = Math.max(0, toNumber(form.sl))
  const exitQuantity = Math.min(Math.max(0, toNumber(form.exit_quantity)), quantity)
  const openQuantity = Math.max(quantity - exitQuantity, 0)

  form.entry_value = roundTo2(quantity * entryPrice)

  const realizedPrice = Math.max(0, toNumber(form.exit_price))
  const realizedPerUnit = form.side === 'Sell' ? entryPrice - realizedPrice : realizedPrice - entryPrice
  const realizedPnl = exitQuantity > 0 && entryPrice > 0 && realizedPrice > 0 ? roundTo2(realizedPerUnit * exitQuantity) : 0

  const unrealizedPerUnit = form.side === 'Sell' ? entryPrice - marketPrice : marketPrice - entryPrice
  const unrealizedPnl = openQuantity > 0 && entryPrice > 0 && marketPrice > 0 ? roundTo2(unrealizedPerUnit * openQuantity) : 0

  form.pnl = roundTo2(realizedPnl + unrealizedPnl)

  form.gain_loss_pct = form.entry_value > 0 ? roundTo2((form.pnl / form.entry_value) * 100) : 0

  form.sl_pct = entryPrice > 0 && stopLoss > 0 ? roundTo2((Math.abs(entryPrice - stopLoss) / entryPrice) * 100) : 0
}

watch(
  [() => form.exit_price, () => form.exit_quantity, () => form.side, () => form.sl, () => liveQuote.value?.current_price],
  () => {
    recomputeDerivedFields()
  },
  { immediate: true },
)

watch(
  lots,
  () => {
    syncSummaryFromLots()
    recomputeDerivedFields()
  },
  { deep: true, immediate: true },
)

async function refreshLiveQuote(forceRefresh = true): Promise<void> {
  const symbol = form.script.trim().toUpperCase()
  if (!editorOpen.value || !symbol || isClosedSession(form.session)) {
    liveQuote.value = null
    return
  }

  try {
    liveQuote.value = await fetchLivePriceQuote(symbol, forceRefresh)
  } catch {
    // Ignore transient quote fetch failures; calculations fall back to user-provided values.
  }
}

function scheduleLiveQuoteRefresh(): void {
  if (livePriceDebounceHandle !== undefined) {
    window.clearTimeout(livePriceDebounceHandle)
  }
  livePriceDebounceHandle = window.setTimeout(() => {
    void refreshLiveQuote(true)
  }, 500)
}

function startLiveQuotePolling(): void {
  if (livePriceIntervalHandle !== undefined) {
    window.clearInterval(livePriceIntervalHandle)
  }
  if (isClosedSession(form.session)) {
    livePriceIntervalHandle = undefined
    return
  }
  livePriceIntervalHandle = window.setInterval(() => {
    void refreshLiveQuote(true)
  }, 15000)
}

function addLotRow(): void {
  lots.push(createLotRow(form.trade_date.trim(), 1, 0, ''))
}

function removeLotRow(index: number): void {
  if (lots.length <= 1) {
    return
  }
  lots.splice(index, 1)
}

const editorTitle = computed(() => (selectedEntry.value ? 'Edit Trade' : 'New Trade'))
const canSubmit = computed(() => {
  const strategyOk = form.trade_strategy !== 'Other' || customTradeStrategy.value.trim().length > 0
  return form.trade_date.trim() && form.script.trim() && form.quantity > 0 && form.entry_price > 0 && strategyOk
})

function applySessionChipFilter(session: 'Open' | 'Close'): void {
  query.session = query.session === session ? 'all' : session
  void loadEntries(true)
}

function resetForm(): void {
  form.trade_date = ''
  form.session = 'Open'
  form.script = ''
  form.trade_strategy = 'RS55'
  form.time_period = 'ShortTerm'
  form.side = 'Buy'
  form.quantity = 1
  form.entry_price = 0
  form.entry_value = 0
  form.exit_quantity = 0
  form.squareoff_date = ''
  form.exit_price = 0
  form.pnl = 0
  form.gain_loss_pct = 0
  form.sl = 0
  form.sl_pct = 0
  form.tp = 0
  form.origination_logic = ''
  form.comment = ''
  form.karma = 5
  form.lots = []
  customTradeStrategy.value = ''
  resetLots()
}

function hydrateFormFromEntry(entry: TradingJournalEntry): void {
  form.trade_date = entry.trade_date
  form.session = entry.session
  form.script = entry.script
  form.trade_strategy = tradeStrategyOptions.some((option) => option.value === entry.trade_strategy)
    ? entry.trade_strategy
    : 'Other'
  customTradeStrategy.value = form.trade_strategy === 'Other' ? entry.trade_strategy : ''
  form.time_period = entry.time_period
  form.side = entry.side
  form.quantity = entry.quantity
  form.entry_price = entry.entry_price
  form.entry_value = entry.entry_value
  form.exit_quantity = entry.exit_quantity
  form.squareoff_date = entry.squareoff_date
  form.exit_price = entry.exit_price
  form.pnl = entry.pnl
  form.gain_loss_pct = entry.gain_loss_pct
  form.sl = entry.sl
  form.sl_pct = entry.sl_pct
  form.tp = entry.tp
  form.origination_logic = entry.origination_logic
  form.comment = entry.comment
  form.karma = entry.karma
  form.lots = entry.lots.map((lot) => ({
    lot_date: lot.lot_date,
    quantity: lot.quantity,
    price: lot.price,
    note: lot.note,
  }))

  lots.splice(
    0,
    lots.length,
    ...(entry.lots.length > 0
      ? entry.lots.map((lot) => ({
          lot_date: lot.lot_date,
          quantity: lot.quantity,
          price: lot.price,
          note: lot.note,
        }))
      : [createLotRow(entry.trade_date, entry.quantity, entry.entry_price, '')]),
  )
}

async function loadEntries(resetPage = false): Promise<void> {
  if (resetPage) {
    query.page = 1
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchTradingJournalEntries(query)
    rows.value = response.items
    meta.total = response.total
    meta.page = response.page
    meta.page_size = response.page_size
    meta.total_pages = response.total_pages
    query.refresh_live_price = false
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to load journal entries'
  } finally {
    loading.value = false
  }
}

async function refreshListLivePrices(): Promise<void> {
  livePricesRefreshing.value = true
  query.include_live_price = true
  query.refresh_live_price = true
  try {
    await loadEntries(false)
  } finally {
    livePricesRefreshing.value = false
  }
}

function openCreateDialog(): void {
  selectedEntry.value = null
  resetForm()
  editorOpen.value = true
  if (!isClosedSession(form.session)) {
    void refreshLiveQuote(true)
  }
  startLiveQuotePolling()
}

function openEditDialog(entry: TradingJournalEntry): void {
  selectedEntry.value = entry
  hydrateFormFromEntry(entry)
  editorOpen.value = true
  if (!isClosedSession(form.session)) {
    void refreshLiveQuote(true)
  }
  startLiveQuotePolling()
}

function requestDelete(entry: TradingJournalEntry): void {
  selectedEntry.value = entry
  deleteConfirmOpen.value = true
}

async function confirmDelete(): Promise<void> {
  if (!selectedEntry.value) {
    deleteConfirmOpen.value = false
    return
  }
  deleting.value = true
  errorMessage.value = ''
  try {
    await deleteTradingJournalEntry(selectedEntry.value.entry_id)
    deleteConfirmOpen.value = false
    await loadEntries()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to delete trade'
  } finally {
    deleting.value = false
  }
}

async function submitEntry(): Promise<void> {
  if (!canSubmit.value) {
    return
  }

  submitting.value = true
  errorMessage.value = ''
  try {
    const payload: TradingJournalEntryUpsertRequest = {
      ...form,
      script: form.script.trim().toUpperCase(),
      trade_strategy: form.trade_strategy === 'Other' ? customTradeStrategy.value.trim() : form.trade_strategy,
      exit_quantity: Math.min(Math.max(0, Number(form.exit_quantity)), Number(form.quantity)),
      lots: lots
        .filter((lot) => Number(lot.quantity) > 0)
        .map((lot) => ({
          lot_date: lot.lot_date.trim() || form.trade_date.trim(),
          quantity: Number(lot.quantity),
          price: Number(lot.price),
          note: lot.note.trim(),
        })),
    }
    if (selectedEntry.value) {
      await updateTradingJournalEntry(selectedEntry.value.entry_id, payload)
    } else {
      await createTradingJournalEntry(payload)
    }
    editorOpen.value = false
    await loadEntries()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to save trade'
  } finally {
    submitting.value = false
  }
}

function exportCsv(): void {
  const url = journalExportUrl({
    search: query.search,
    session: query.session,
    trade_strategy: query.trade_strategy,
    time_period: query.time_period,
    sort_by: query.sort_by,
    sort_order: query.sort_order,
  })
  window.open(url, '_blank')
}

onMounted(async () => {
  await loadEntries()
})

onUnmounted(() => {
  clearLivePriceTimers()
})

watch(
  () => editorOpen.value,
  (open) => {
    if (!open) {
      clearLivePriceTimers()
      return
    }
    startLiveQuotePolling()
  },
)

watch(
  () => form.script,
  () => {
    if (editorOpen.value) {
      scheduleLiveQuoteRefresh()
    }
  },
)

watch(
  () => form.trade_date,
  (tradeDate) => {
    if (!tradeDate) {
      return
    }
    lots.forEach((lot) => {
      if (!lot.lot_date) {
        lot.lot_date = tradeDate
      }
    })
  },
)

watch(
  () => form.trade_strategy,
  (strategy) => {
    if (strategy !== 'Other') {
      customTradeStrategy.value = ''
    }
  },
)

watch(
  () => form.session,
  () => {
    if (!editorOpen.value) {
      return
    }
    if (isClosedSession(form.session)) {
      clearLivePriceTimers()
      liveQuote.value = null
    } else {
      void refreshLiveQuote(true)
      startLiveQuotePolling()
    }
    recomputeDerivedFields()
  },
)

function money(value: number): string {
  return `Rs ${value.toLocaleString('en-IN')}`
}

function pct(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function pnlColor(value: number): 'success' | 'error' | 'default' {
  if (value > 0) {
    return 'success'
  }
  if (value < 0) {
    return 'error'
  }
  return 'default'
}

function pnlTone(value: number): 'positive' | 'negative' | 'flat' {
  if (value > 0) {
    return 'positive'
  }
  if (value < 0) {
    return 'negative'
  }
  return 'flat'
}

function formatRangeLabel(): string {
  if (meta.total <= 0 || rows.value.length <= 0) {
    return '0 of 0'
  }
  const start = (meta.page - 1) * meta.page_size + 1
  const end = start + rows.value.length - 1
  return `${start}-${end} of ${meta.total}`
}

function onJournalPageChange(nextPage: number): void {
  query.page = Number(nextPage || 1)
  void loadEntries(false)
}
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card class="journal-card journal-hero mb-4">
        <v-card-title class="card-heading d-flex justify-space-between align-start flex-wrap ga-2">
          <div>
            <div class="journal-hero-title">Trading Journal</div>
            <div class="text-body-2 text-medium-emphasis journal-hero-subtitle">
              Structured log for entries, exits, risk controls, and post-trade learning.
            </div>
            <div class="journal-hero-chips mt-3">
              <v-chip
                v-for="chip in journalSummary"
                :key="chip.label"
                size="small"
                :variant="query.session === chip.session ? 'flat' : 'tonal'"
                :color="chip.color"
                class="journal-metric-chip"
                :class="{ 'is-active': query.session === chip.session }"
                @click="applySessionChipFilter(chip.session)"
              >
                <span class="journal-metric-label">{{ chip.label }}</span>
                <strong class="journal-metric-value">{{ chip.value }}</strong>
              </v-chip>
            </div>
          </div>
          <div class="journal-toolbar-actions">
            <v-btn class="journal-toolbar-btn" color="primary" variant="flat" prepend-icon="mdi-table-plus" @click="openCreateDialog">New Trade</v-btn>
            <v-btn
              class="journal-toolbar-btn"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-refresh"
              :loading="livePricesRefreshing"
              @click="refreshListLivePrices"
            >
              Refresh Prices
            </v-btn>
            <v-btn class="journal-toolbar-btn" color="success" variant="tonal" prepend-icon="mdi-file-export-outline" @click="exportCsv">Export CSV</v-btn>
          </div>
        </v-card-title>

        <v-card-text>
          <v-alert
            v-if="errorMessage"
            type="error"
            variant="tonal"
            class="mb-3"
            closable
            @click:close="errorMessage = ''"
          >
            {{ errorMessage }}
          </v-alert>

          <v-row class="mb-2">
            <v-col cols="12" md="5">
              <v-text-field
                v-model="query.search"
                label="Search"
                placeholder="Script, strategy, logic, comment"
                prepend-inner-icon="mdi-magnify"
                clearable
                @keyup.enter="loadEntries(true)"
                @click:clear="loadEntries(true)"
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="query.session"
                :items="sessionOptions"
                item-title="title"
                item-value="value"
                label="Open/Close"
                @update:model-value="loadEntries(true)"
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="query.trade_strategy"
                :items="strategyFilterOptions"
                item-title="title"
                item-value="value"
                label="Strategy"
                @update:model-value="loadEntries(true)"
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="query.time_period"
                :items="timePeriodFilterOptions"
                item-title="title"
                item-value="value"
                label="Time Period"
                @update:model-value="loadEntries(true)"
              />
            </v-col>
          </v-row>


          <v-data-table
            class="journal-table polished-table"
            :headers="tableHeaders"
            :items="rows"
            item-value="entry_id"
            show-expand
            density="compact"
            hide-default-footer
            :items-per-page="-1"
            fixed-header
            height="420"
            :loading="loading"
          >
            <template #item.side="{ item }">
              <v-chip :color="item.side === 'Buy' ? 'success' : 'error'" size="small" variant="tonal">
                {{ item.side }}
              </v-chip>
            </template>

            <template #item.lots="{ item }">
              <v-chip size="small" color="primary" variant="tonal">
                {{ item.lots?.length || 0 }} fill{{ (item.lots?.length || 0) === 1 ? '' : 's' }}
              </v-chip>
            </template>

            <template #item.trade_strategy="{ item }">
              <span>{{ item.trade_strategy || '--' }}</span>
            </template>

            <template #item.time_period="{ item }">
              <v-chip size="small" :color="item.time_period === 'LongTerm' ? 'indigo' : 'teal'" variant="tonal">
                {{ item.time_period }}
              </v-chip>
            </template>

            <template #item.exit_quantity="{ item }">
              <span>{{ item.exit_quantity || 0 }}</span>
            </template>

            <template #item.entry_price="{ item }">{{ money(item.entry_price) }}</template>
            <template #item.current_price="{ item }">
              <span v-if="item.current_price === null || item.current_price === undefined" class="text-medium-emphasis">--</span>
              <span v-else>{{ money(item.current_price) }}</span>
            </template>
            <template #item.entry_value="{ item }">{{ money(item.entry_value) }}</template>
            <template #item.exit_price="{ item }">{{ money(item.exit_price) }}</template>

            <template #item.pnl="{ item }">
              <v-chip :color="pnlColor(item.pnl)" size="small" variant="tonal">
                {{ money(item.pnl) }}
              </v-chip>
            </template>

            <template #item.gain_loss_pct="{ item }">
              <v-chip :color="pnlColor(item.gain_loss_pct)" size="small" variant="tonal">
                {{ pct(item.gain_loss_pct) }}
              </v-chip>
            </template>

            <template #item.sl="{ item }">{{ money(item.sl) }}</template>
            <template #item.sl_pct="{ item }">{{ pct(item.sl_pct) }}</template>
            <template #item.tp="{ item }">{{ money(item.tp) }}</template>

            <template #item.actions="{ item }">
              <div class="table-action-group">
                <v-tooltip text="Edit trade" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-pencil-outline"
                      size="small"
                      variant="tonal"
                      color="primary"
                      @click="openEditDialog(item)"
                    />
                  </template>
                </v-tooltip>

                <v-tooltip text="Delete trade" location="top">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-delete-outline"
                      size="small"
                      variant="tonal"
                      color="error"
                      @click="requestDelete(item)"
                    />
                  </template>
                </v-tooltip>
              </div>
            </template>

            <template #expanded-row="{ columns, item }">
              <tr>
                <td :colspan="columns.length" class="pa-0">
                  <div class="pa-4 journal-expanded-panel">
                    <v-row dense>
                      <v-col cols="12" md="8">
                        <v-card variant="outlined" class="mb-3 journal-panel-card journal-panel-card-soft">
                          <v-card-title class="text-subtitle-2">Entry Fills</v-card-title>
                          <v-card-text>
                            <v-table density="compact">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Qty</th>
                                  <th>Price</th>
                                  <th>Note</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr v-for="lot in item.lots || []" :key="lot.lot_id">
                                  <td>{{ lot.lot_date }}</td>
                                  <td>{{ lot.quantity }}</td>
                                  <td>{{ money(lot.price) }}</td>
                                  <td>{{ lot.note || '--' }}</td>
                                </tr>
                              </tbody>
                            </v-table>
                          </v-card-text>
                        </v-card>

                        <v-card v-if="item.exit_quantity > 0" variant="outlined" class="journal-panel-card journal-panel-card-warm">
                          <v-card-title class="text-subtitle-2">Exit Leg</v-card-title>
                          <v-card-text>
                            <v-table density="compact">
                              <thead>
                                <tr>
                                  <th>Date</th>
                                  <th>Qty</th>
                                  <th>Price</th>
                                  <th>P/L</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <td>{{ item.squareoff_date || item.updated_at.slice(0, 10) }}</td>
                                  <td>{{ item.exit_quantity }}</td>
                                  <td>{{ money(item.exit_price) }}</td>
                                  <td>{{ money(item.realized_pnl ?? 0) }}</td>
                                </tr>
                              </tbody>
                            </v-table>
                          </v-card-text>
                        </v-card>
                      </v-col>

                      <v-col cols="12" md="4">
                        <v-card variant="outlined" class="pa-0 h-100 journal-ledger-card">
                          <v-card-title class="text-subtitle-2 journal-ledger-title">Position Ledger</v-card-title>
                          <v-card-text class="pa-0">
                            <div class="journal-ledger-list">
                              <div class="journal-ledger-row">
                                <span>Total Quantity</span>
                                <strong>{{ item.quantity }}</strong>
                              </div>
                              <div class="journal-ledger-row">
                                <span>Open Quantity</span>
                                <strong>{{ item.open_quantity ?? item.quantity }}</strong>
                              </div>
                              <div class="journal-ledger-row">
                                <span>Average Entry</span>
                                <strong>{{ money(item.entry_price) }}</strong>
                              </div>
                              <div class="journal-ledger-row">
                                <span>Current Price</span>
                                <strong>{{ item.current_price ? money(item.current_price) : '--' }}</strong>
                              </div>
                              <div class="journal-ledger-row">
                                <span>Realized P/L</span>
                                <strong :class="`is-${pnlTone(item.realized_pnl ?? 0)}`">{{ money(item.realized_pnl ?? 0) }}</strong>
                              </div>
                              <div class="journal-ledger-row">
                                <span>Unrealized P/L</span>
                                <strong :class="`is-${pnlTone(item.unrealized_pnl ?? 0)}`">{{ money(item.unrealized_pnl ?? 0) }}</strong>
                              </div>
                              <div class="journal-ledger-row journal-ledger-total">
                                <span>Total P/L</span>
                                <strong :class="`is-${pnlTone(item.pnl)}`">{{ money(item.pnl) }}</strong>
                              </div>
                            </div>
                          </v-card-text>
                        </v-card>
                      </v-col>
                    </v-row>
                  </div>
                </td>
              </tr>
            </template>

            <template #no-data>
              <div class="journal-empty-state">
                <v-icon size="26" color="primary" icon="mdi-notebook-plus-outline" />
                <div class="journal-empty-title">No journal entries yet</div>
                <div class="journal-empty-subtitle">Capture your first trade to start tracking execution quality and your decision process.</div>
              </div>
            </template>
          </v-data-table>

          <div class="d-flex justify-space-between align-center mt-3 flex-wrap ga-3">
            <div class="text-body-2 text-medium-emphasis">{{ formatRangeLabel() }}</div>
            <div class="d-flex align-center ga-2 flex-wrap">
              <v-select
                v-model="query.page_size"
                :items="[10, 15, 25, 50, 100]"
                label="Page Size"
                density="compact"
                hide-details
                style="min-width: 140px"
                @update:model-value="loadEntries(true)"
              />
              <v-pagination
                v-model="query.page"
                :length="meta.total_pages"
                total-visible="6"
                @update:model-value="onJournalPageChange"
              />
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <v-dialog v-model="editorOpen" max-width="980">
    <v-card>
      <v-card-title>{{ editorTitle }}</v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model="form.trade_date" label="Date" type="date" /></v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="form.session"
              :items="[{ title: 'Open', value: 'Open' }, { title: 'Close', value: 'Close' }]"
              item-title="title"
              item-value="value"
              label="Open/Close"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model="form.script" label="Script" /></v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="form.side"
              :items="[{ title: 'Buy', value: 'Buy' }, { title: 'Sell', value: 'Sell' }]"
              item-title="title"
              item-value="value"
              label="Buy/Sell"
            />
          </v-col>

          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="form.trade_strategy"
              :items="tradeStrategyOptions"
              item-title="title"
              item-value="value"
              label="Trade Strategy"
            />
          </v-col>
          <v-col v-if="form.trade_strategy === 'Other'" cols="12" sm="6" md="3">
            <v-text-field
              v-model="customTradeStrategy"
              label="Custom Strategy"
              placeholder="Type your strategy name"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="form.time_period"
              :items="timePeriodOptions"
              item-title="title"
              item-value="value"
              label="Time Period"
            />
          </v-col>

          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.quantity" label="Total Quantity" type="number" min="1" readonly hint="Derived from fills" persistent-hint /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.entry_price" label="Avg Entry" type="number" min="0" step="0.01" readonly hint="Weighted average from fills" persistent-hint /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.entry_value" label="Entry Value" type="number" min="0" step="0.01" hint="Auto: Total Qty x Avg Entry" persistent-hint readonly /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model="form.squareoff_date" label="SquareOff Date" type="date" /></v-col>

          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.exit_price" label="Exit Price" type="number" min="0" step="0.01" /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.exit_quantity" label="Exit Qty" type="number" min="0" step="1" hint="Qty sold from this position" persistent-hint /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.pnl" label="Profit/Loss" type="number" step="0.01" hint="Auto from Side, Entry, Exit and Quantity" persistent-hint readonly /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.gain_loss_pct" label="% Gain/Loss" type="number" step="0.01" hint="Auto from current price when Exit Price is empty" persistent-hint readonly /></v-col>
          <v-col cols="12" sm="6" md="3"><v-text-field v-model.number="form.karma" label="Karma" type="number" min="0" max="10" /></v-col>

          <v-col cols="12">
            <v-alert type="info" variant="tonal" class="mb-3">
              Add one row per fill. When you scale in later, the journal recalculates the weighted average entry and total value.
            </v-alert>
            <v-card variant="tonal" class="pa-3 journal-fill-card">
              <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-3">
                <div class="text-subtitle-2">Entry Fills</div>
                <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addLotRow">Add Fill</v-btn>
              </div>

              <v-row v-for="(lot, index) in lots" :key="index" class="mb-2">
                <v-col cols="12" sm="4" md="3">
                  <v-text-field v-model="lot.lot_date" label="Fill Date" type="date" />
                </v-col>
                <v-col cols="12" sm="3" md="2">
                  <v-text-field v-model.number="lot.quantity" label="Qty" type="number" min="1" />
                </v-col>
                <v-col cols="12" sm="3" md="2">
                  <v-text-field v-model.number="lot.price" label="Price" type="number" min="0" step="0.01" />
                </v-col>
                <v-col cols="12" sm="12" md="4">
                  <v-text-field v-model="lot.note" label="Note" placeholder="Optional fill note" />
                </v-col>
                <v-col cols="12" md="1" class="d-flex align-center justify-end">
                  <v-btn icon="mdi-close" size="small" variant="text" color="error" :disabled="lots.length <= 1" @click="removeLotRow(index)" />
                </v-col>
              </v-row>
            </v-card>
          </v-col>

          <v-col cols="12" sm="4"><v-text-field v-model.number="form.sl" label="SL" type="number" min="0" step="0.01" /></v-col>
          <v-col cols="12" sm="4"><v-text-field v-model.number="form.sl_pct" label="SL %" type="number" step="0.01" hint="Auto: |Entry - SL| divided by Entry" persistent-hint readonly /></v-col>
          <v-col cols="12" sm="4"><v-text-field v-model.number="form.tp" label="TP" type="number" min="0" step="0.01" /></v-col>

          <v-col cols="12"><v-textarea v-model="form.origination_logic" label="Origination Logic" rows="3" auto-grow /></v-col>
          <v-col cols="12"><v-textarea v-model="form.comment" label="Comment" rows="2" auto-grow /></v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="justify-end">
        <v-btn variant="text" color="secondary" @click="editorOpen = false">Cancel</v-btn>
        <v-btn variant="flat" color="primary" :disabled="!canSubmit" :loading="submitting" @click="submitEntry">Save Trade</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="deleteConfirmOpen" max-width="420">
    <v-card>
      <v-card-title>Delete Trade</v-card-title>
      <v-card-text>Are you sure you want to delete this trade entry?</v-card-text>
      <v-card-actions class="justify-end">
        <v-btn variant="text" color="secondary" @click="deleteConfirmOpen = false">Cancel</v-btn>
        <v-btn variant="flat" color="error" :loading="deleting" @click="confirmDelete">Delete</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
