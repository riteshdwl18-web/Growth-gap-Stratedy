import { API_BASE } from './auth'

export type JournalSide = 'Buy' | 'Sell'
export type JournalSession = 'Open' | 'Close'

export type TradingJournalLot = {
  lot_id: number
  lot_date: string
  quantity: number
  price: number
  note: string
}

export type TradingJournalLotUpsertRequest = {
  lot_date: string
  quantity: number
  price: number
  note: string
}

export type TradingJournalEntry = {
  entry_id: string
  trade_date: string
  session: JournalSession
  script: string
  trade_strategy: string
  time_period: 'ShortTerm' | 'LongTerm'
  side: JournalSide
  quantity: number
  entry_price: number
  entry_value: number
  exit_quantity: number
  squareoff_date: string
  exit_price: number
  pnl: number
  gain_loss_pct: number
  sl: number
  sl_pct: number
  tp: number
  origination_logic: string
  comment: string
  karma: number
  lots: TradingJournalLot[]
  open_quantity?: number
  realized_pnl?: number
  unrealized_pnl?: number
  current_price?: number | null
  live_price_as_of?: string | null
  created_at: string
  updated_at: string
}

export type TradingJournalEntryUpsertRequest = {
  trade_date: string
  session: JournalSession
  script: string
  trade_strategy: string
  time_period: 'ShortTerm' | 'LongTerm'
  side: JournalSide
  quantity: number
  entry_price: number
  entry_value: number
  exit_quantity: number
  squareoff_date: string
  exit_price: number
  pnl: number
  gain_loss_pct: number
  sl: number
  sl_pct: number
  tp: number
  origination_logic: string
  comment: string
  karma: number
  lots: TradingJournalLotUpsertRequest[]
}

export type TradingJournalEntriesListResponse = {
  items: TradingJournalEntry[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type LivePriceQuote = {
  symbol: string
  current_price: number | null
  quote_as_of: string | null
  source: string | null
}

export type TradingJournalListQuery = {
  search: string
  session: 'all' | JournalSession
  trade_strategy: 'all' | 'RS55' | 'Growth-Gap' | 'Range-Bound' | 'Other'
  time_period: 'all' | 'ShortTerm' | 'LongTerm'
  sort_by:
    | 'trade_date'
    | 'squareoff_date'
    | 'script'
    | 'trade_strategy'
    | 'time_period'
    | 'side'
    | 'quantity'
    | 'entry_price'
    | 'exit_price'
    | 'pnl'
    | 'gain_loss_pct'
    | 'karma'
    | 'updated_at'
  sort_order: 'asc' | 'desc'
  include_live_price?: boolean
  refresh_live_price?: boolean
  page: number
  page_size: number
}

function buildQuery(params: Record<string, string | number | boolean>): string {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    query.set(key, String(value))
  })
  return query.toString()
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    ...init,
    credentials: 'include',
  })
}

async function ensureOk(response: Response, fallbackMessage: string): Promise<void> {
  if (response.ok) {
    return
  }
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  throw new Error(payload?.detail || fallbackMessage)
}

export async function fetchTradingJournalEntries(
  query: TradingJournalListQuery,
): Promise<TradingJournalEntriesListResponse> {
  const response = await apiFetch(
    `${API_BASE}/api/journal/entries?${buildQuery({
      search: query.search,
      session: query.session,
      trade_strategy: query.trade_strategy,
      time_period: query.time_period,
      sort_by: query.sort_by,
      sort_order: query.sort_order,
      include_live_price: query.include_live_price ?? false,
      refresh_live_price: query.refresh_live_price ?? false,
      page: query.page,
      page_size: query.page_size,
    })}`,
  )
  await ensureOk(response, 'Failed to load journal entries')
  return (await response.json()) as TradingJournalEntriesListResponse
}

export async function createTradingJournalEntry(
  payload: TradingJournalEntryUpsertRequest,
): Promise<TradingJournalEntry> {
  const response = await apiFetch(`${API_BASE}/api/journal/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await ensureOk(response, 'Failed to create journal entry')
  return (await response.json()) as TradingJournalEntry
}

export async function updateTradingJournalEntry(
  entryId: string,
  payload: TradingJournalEntryUpsertRequest,
): Promise<TradingJournalEntry> {
  const response = await apiFetch(`${API_BASE}/api/journal/entries/${encodeURIComponent(entryId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await ensureOk(response, 'Failed to update journal entry')
  return (await response.json()) as TradingJournalEntry
}

export async function deleteTradingJournalEntry(entryId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/api/journal/entries/${encodeURIComponent(entryId)}`, {
    method: 'DELETE',
  })
  await ensureOk(response, 'Failed to delete journal entry')
}

export function journalExportUrl(query: Omit<TradingJournalListQuery, 'page' | 'page_size'>): string {
  return `${API_BASE}/api/journal/entries/export.csv?${buildQuery({
    search: query.search,
    session: query.session,
    trade_strategy: query.trade_strategy,
    time_period: query.time_period,
    sort_by: query.sort_by,
    sort_order: query.sort_order,
  })}`
}

export async function fetchLivePriceQuote(symbol: string, refresh = true): Promise<LivePriceQuote> {
  const response = await apiFetch(
    `${API_BASE}/api/market/quote?${buildQuery({
      symbol,
      refresh,
    })}`,
  )
  await ensureOk(response, 'Failed to fetch live price')
  return (await response.json()) as LivePriceQuote
}
