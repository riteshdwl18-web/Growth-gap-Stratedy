export type AuthStatusResponse = {
  authenticated: boolean
  email: string | null
  username?: string | null
  signup_required: boolean
}

export type LoginPayload = {
  email: string
  password: string
}

export type SignupPayload = {
  email: string
  password: string
}

export type ChangePasswordPayload = {
  current_password: string
  new_password: string
}

export type MessageResponse = {
  message: string
}

export type ForgotPasswordPayload = {
  email: string
}

export type ResetPasswordPayload = {
  token: string
  new_password: string
}

export const API_BASE =
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

const AUTH_STATUS_CACHE_TTL_MS = 60000
let cachedAuthStatus: { data: AuthStatusResponse; expiresAt: number } | null = null

function invalidateAuthStatusCache(): void {
  cachedAuthStatus = null
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// Throws on network-level failure (offline, connection reset, timeout) so the
// caller can distinguish "couldn't reach the server" from a real "not authenticated"
// answer, instead of treating a transient blip as a hard logout.
async function fetchAuthMeOnce(): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE}/api/auth/me`, {
    credentials: 'include',
  })
  if (!response.ok) {
    return { authenticated: false, email: null, username: null, signup_required: false }
  }
  return (await response.json()) as AuthStatusResponse
}

export async function getAuthStatus(): Promise<AuthStatusResponse> {
  if (cachedAuthStatus && cachedAuthStatus.expiresAt > Date.now()) {
    return cachedAuthStatus.data
  }

  let data: AuthStatusResponse
  try {
    data = await fetchAuthMeOnce()
  } catch {
    // Network-level failure on the first attempt is often a transient blip
    // (cold connection on page load, brief proxy hiccup) rather than a real
    // logout — retry once before giving up.
    try {
      await sleep(300)
      data = await fetchAuthMeOnce()
    } catch {
      return { authenticated: false, email: null, username: null, signup_required: false }
    }
  }

  cachedAuthStatus = { data, expiresAt: Date.now() + AUTH_STATUS_CACHE_TTL_MS }
  return data
}

export async function login(payload: LoginPayload): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail || 'Login failed')
  }

  invalidateAuthStatusCache()
  return (await response.json()) as AuthStatusResponse
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  invalidateAuthStatusCache()
}

export async function signup(payload: SignupPayload): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE}/api/auth/signup`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail || 'Signup failed')
  }

  invalidateAuthStatusCache()
  return (await response.json()) as AuthStatusResponse
}

export async function changePassword(payload: ChangePasswordPayload): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE}/api/auth/change-password`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail || 'Password change failed')
  }

  return (await response.json()) as MessageResponse
}

export async function forgotPassword(payload: ForgotPasswordPayload): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE}/api/auth/forgot-password`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail || 'Forgot password request failed')
  }

  return (await response.json()) as MessageResponse
}

export async function resetPassword(payload: ResetPasswordPayload): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE}/api/auth/reset-password`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail || 'Password reset failed')
  }

  return (await response.json()) as MessageResponse
}

