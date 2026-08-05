export type AuthStatusResponse = {
  authenticated: boolean
  username: string | null
  signup_required: boolean
  google_oauth_available: boolean
}

export type LoginPayload = {
  username: string
  password: string
}

export type SignupPayload = {
  username: string
  password: string
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

export async function getAuthStatus(): Promise<AuthStatusResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      credentials: 'include',
    })
    if (!response.ok) {
      return { authenticated: false, username: null, signup_required: false, google_oauth_available: false }
    }
    return (await response.json()) as AuthStatusResponse
  } catch {
    return { authenticated: false, username: null, signup_required: false, google_oauth_available: false }
  }
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

  return (await response.json()) as AuthStatusResponse
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
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

  return (await response.json()) as AuthStatusResponse
}

export function startGoogleSignIn(redirectPath = '/dashboard'): void {
  const redirectUrl = new URL(redirectPath, window.location.origin).toString()
  const oauthUrl = `${API_BASE}/api/auth/google/start?redirect_uri=${encodeURIComponent(redirectUrl)}`
  window.location.assign(oauthUrl)
}
