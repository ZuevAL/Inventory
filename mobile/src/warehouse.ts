import { useSyncExternalStore } from 'react'
import { AppState, Platform } from 'react-native'

import { operationId, readLocal, readSession, writeLocal, writeSession } from './storage'
import {
  projectSnapshot, validatedInput,
  type CachedWarehouse, type Operation, type OperationInput, type PendingOperation,
  type Snapshot, type StoredSession, type User,
} from './warehouse-model'

export * from './warehouse-model'

type Config = { url: string }
type AuthStep = { status: 'confirm_login' | 'password_setup'; message: string }
type TokenPair = {
  status: 'authenticated'
  access_token: string
  refresh_token: string
  expires_in: number
  session_expires_at: number
  user: User
}
type PendingAuth =
  | (AuthStep & { status: 'confirm_login'; confirmation_token: string })
  | (AuthStep & { status: 'password_setup'; password_setup_token: string })

type State = {
  config: Config
  session: { user: User } | null
  authReady: boolean
  authStep: AuthStep | null
  snapshot: Snapshot | null
  pending: PendingOperation[]
  loading: boolean
  syncing: boolean
  online: boolean
  error: string | null
}

class ApiError extends Error {
  constructor(readonly status: number, message: string, readonly code?: string) {
    super(message)
  }
}

const apiPrefix = '/api/v1'
const emptyWarehouse: CachedWarehouse = { snapshot: null, pending: [] }
const defaultUrl = (process.env.EXPO_PUBLIC_API_URL?.trim() ||
  (Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://127.0.0.1:8000')).replace(/\/+$/, '')
const initial: State = {
  config: { url: defaultUrl }, session: null, authReady: false, authStep: null,
  snapshot: null, pending: [], loading: true, syncing: false, online: false, error: null,
}

let state = initial
let warehouse = emptyWarehouse
let session: StoredSession | null = null
let access: { token: string; expiresAt: number } | null = null
let pendingAuth: PendingAuth | null = null
let work = Promise.resolve()
let restoreTask: Promise<void> | undefined
let syncTask: Promise<void> | undefined
let detach: (() => void) | undefined
const listeners = new Set<() => void>()

function notify(changes: Partial<State>) {
  state = { ...state, ...changes }
  listeners.forEach(listener => listener())
}

function exclusive<T>(action: () => Promise<T>): Promise<T> {
  const result = work.then(action)
  work = result.then(() => undefined, () => undefined)
  return result
}

function cacheKey(user: User) {
  return `warehouse:${state.config.url}:${user.id}:${user.login}`
}

function loadWarehouse(value: CachedWarehouse) {
  warehouse = value
  notify({ snapshot: projectSnapshot(value), pending: value.pending })
}

async function saveWarehouse(value: CachedWarehouse) {
  if (!session) throw new Error('Войдите в приложение')
  await writeLocal(cacheKey(session.user), value)
  loadWarehouse(value)
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить действие'
}

async function request<T>(path: string, body?: object, token?: string): Promise<T> {
  const controller = new AbortController()
  const deadline = setTimeout(() => controller.abort(), 6500)
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const response = await fetch(state.config.url + apiPrefix + path, {
      method: body ? 'POST' : 'GET',
      body: body && JSON.stringify(body),
      headers,
      signal: controller.signal,
      credentials: 'omit',
    })
    if (response.status === 204) return undefined as T

    const data = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : data?.detail?.[0]?.msg
      throw new ApiError(
        response.status,
        response.status >= 500
          ? 'Сервер склада временно недоступен'
          : detail || `Ошибка сервера (${response.status})`,
        data?.code,
      )
    }
    if (!data) throw new ApiError(0, 'Ответ сервера имеет неожиданный формат')
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, 'Нет связи с сервером склада')
  } finally {
    clearTimeout(deadline)
  }
}

async function acceptTokens(pair: TokenPair) {
  const next = {
    refreshToken: pair.refresh_token,
    expiresAt: pair.session_expires_at * 1000,
    user: pair.user,
    url: state.config.url,
  }
  const sameUser = session?.user.id === pair.user.id && session.user.login === pair.user.login
  const cached = sameUser ? warehouse : await readLocal<CachedWarehouse>(cacheKey(pair.user)) ?? emptyWarehouse
  await writeSession(next)
  session = next
  access = { token: pair.access_token, expiresAt: Date.now() + pair.expires_in * 1000 }
  pendingAuth = null
  loadWarehouse(cached)
  notify({ session: { user: pair.user }, authStep: null, error: null, loading: !cached.snapshot })
}

async function forgetSession(error: string | null) {
  try {
    await writeSession(null)
  } finally {
    session = null
    access = null
    pendingAuth = null
    warehouse = emptyWarehouse
    notify({
      session: null, authStep: null, snapshot: null, pending: [],
      online: false, loading: false, error,
    })
  }
}

function restore() {
  restoreTask ??= exclusive(async () => {
    try {
      const url = await readLocal<string>('server-url') ?? defaultUrl
      notify({ config: { url } })
      const saved = await readSession()
      if (saved && saved.url === url && saved.expiresAt > Date.now()) {
        const cached = await readLocal<CachedWarehouse>(cacheKey(saved.user)) ?? emptyWarehouse
        session = saved
        loadWarehouse(cached)
        notify({ session: { user: saved.user }, loading: !cached.snapshot })
      } else {
        if (saved) await writeSession(null)
        notify({ loading: false })
      }
    } catch (error) {
      notify({ error: message(error), loading: false })
    } finally {
      notify({ authReady: true })
    }
  })
  return restoreTask
}

async function usableAccess(): Promise<string> {
  const stored = session
  if (!stored) throw new ApiError(401, 'Войдите в приложение')
  if (stored.expiresAt <= Date.now()) {
    const expired = 'Сессия завершена. Войдите снова'
    await forgetSession(expired)
    throw new ApiError(401, expired)
  }
  if (access && access.expiresAt > Date.now() + 5000) return access.token

  // Refresh is single-use. Check connectivity and record the attempt before sending it.
  await request('/health')
  if (stored.refreshUncertain) {
    const expired = 'Не удалось подтвердить обновление сессии. Войдите снова'
    await forgetSession(expired)
    throw new ApiError(401, expired)
  }
  const attempted = { ...stored, refreshUncertain: true }
  await writeSession(attempted)
  session = attempted
  const pair = await request<TokenPair>('/auth/refresh', { refresh_token: stored.refreshToken })
  await acceptTokens(pair)
  return pair.access_token
}

async function authorized<T>(path: string, body?: object): Promise<T> {
  try {
    const token = await usableAccess()
    try {
      return await request<T>(path, body, token)
    } catch (error) {
      if (!(error instanceof ApiError) || error.code !== 'token_expired') throw error
      access = null
      return await request<T>(path, body, await usableAccess())
    }
  } catch (error) {
    if (session && error instanceof ApiError && error.status === 401) await forgetSession(error.message)
    throw error
  }
}

async function pushAndPull() {
  if (!session) return
  notify({ syncing: true, loading: !warehouse.snapshot })
  const applied = new Set<string>()
  try {
    for (const { status, error: _error, ...operation } of warehouse.pending) {
      if (status !== 'queued') continue
      try {
        await authorized<Operation>('/warehouse/operations', operation)
        applied.add(operation.operation_id)
      } catch (error) {
        if (!(error instanceof ApiError) || ![400, 404, 409, 422].includes(error.status) ||
            error.message === 'Not Found') throw error
        await saveWarehouse({
          ...warehouse,
          pending: warehouse.pending.map(item => item.operation_id === operation.operation_id
            ? { ...item, status: 'conflict', error: error.message }
            : item),
        })
      }
    }

    // Keep acknowledged entries until the new server snapshot is saved with the outbox.
    // A crash or disconnect here safely replays their existing operation IDs.
    const snapshot = await authorized<Snapshot>('/warehouse/snapshot')
    await saveWarehouse({
      snapshot,
      pending: warehouse.pending.filter(item => !applied.has(item.operation_id)),
    })
    notify({ online: true, error: null })
  } catch (error) {
    notify({ online: false, error: message(error) })
  } finally {
    notify({ syncing: false, loading: false })
  }
}

function sync() {
  if (syncTask) return syncTask
  void restore()
  syncTask = exclusive(pushAndPull).finally(() => { syncTask = undefined })
  return syncTask
}

async function submit(input: OperationInput): Promise<'applied' | 'queued'> {
  await restore()
  return exclusive(async () => {
    if (!session || session.expiresAt <= Date.now()) throw new Error('Войдите в приложение')
    if (session.user.recovery_required) throw new Error('Сохраните резервный код в веб-панели')
    if (!state.snapshot) throw new Error('Сначала загрузите данные склада')
    const id = operationId()
    const operation: PendingOperation = {
      ...validatedInput(state.snapshot, input),
      operation_id: id, status: 'queued', error: null,
    }
    const wasOnline = state.online
    await saveWarehouse({ ...warehouse, pending: [...warehouse.pending, operation] })
    if (!wasOnline) {
      void sync()
      return 'queued'
    }
    await pushAndPull()
    if (!session) return 'queued'
    const pending = warehouse.pending.find(item => item.operation_id === id)
    if (pending?.status === 'conflict') throw new Error(pending.error ?? 'Сервер отклонил операцию')
    return pending ? 'queued' : 'applied'
  })
}

async function discard(id: string) {
  await restore()
  await exclusive(async () => {
    await saveWarehouse({
      ...warehouse,
      pending: warehouse.pending.filter(item => item.operation_id !== id || item.status !== 'conflict'),
    })
  })
}

async function configure(config: Config) {
  const value = config.url.trim().replace(/\/+$/, '')
  if (!/^https?:\/\/[^/@\s?#]+(?:\/[^\s?#]*)?$/.test(value)) {
    throw new Error('Введите адрес сервера, начиная с http:// или https://')
  }
  await restore()
  await exclusive(async () => {
    if (session) throw new Error('Выйдите из аккаунта перед сменой сервера')
    await writeLocal('server-url', value)
    pendingAuth = null
    notify({ config: { url: value }, authStep: null, error: null })
  })
}

async function login(login: string, password: string) {
  await restore()
  await exclusive(async () => {
    const result = await request<TokenPair | PendingAuth>('/auth/login', { login: login.trim(), password })
    if (result.status === 'authenticated') {
      await acceptTokens(result)
    } else {
      pendingAuth = result
      notify({ authStep: { status: result.status, message: result.message }, error: null })
    }
  })
  if (session) void sync()
}

async function confirmLogin() {
  await exclusive(async () => {
    const step = pendingAuth
    if (step?.status !== 'confirm_login') throw new Error('Повторите вход')
    await acceptTokens(await request<TokenPair>('/auth/confirm-login', {
      confirmation_token: step.confirmation_token, confirm: true,
    }))
  })
  void sync()
}

async function setupPassword(password: string) {
  await exclusive(async () => {
    const step = pendingAuth
    if (step?.status !== 'password_setup') throw new Error('Повторите вход')
    await acceptTokens(await request<TokenPair>('/auth/password/setup', {
      password_setup_token: step.password_setup_token, new_password: password,
    }))
  })
  void sync()
}

function cancelAuth() {
  pendingAuth = null
  notify({ authStep: null, error: null })
}

async function logout() {
  await restore()
  await exclusive(async () => {
    try {
      if (session) await authorized('/auth/logout', {})
    } finally {
      await forgetSession(null)
    }
  })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  if (!detach) {
    void sync()
    const appState = AppState.addEventListener('change', status => {
      if (status === 'active') void sync()
    })
    const timer = setInterval(() => {
      if (AppState.currentState !== 'background') void sync()
    }, 15_000)
    const online = () => { void sync() }
    if (Platform.OS === 'web') window.addEventListener('online', online)
    detach = () => {
      appState.remove()
      clearInterval(timer)
      if (Platform.OS === 'web') window.removeEventListener('online', online)
    }
  }
  return () => {
    listeners.delete(listener)
    if (!listeners.size) {
      detach?.()
      detach = undefined
    }
  }
}

function getState() {
  return state
}

export function useWarehouse() {
  const result = useSyncExternalStore(subscribe, getState, () => initial)
  return {
    ...result, sync, submit, discard, configure, login, confirmLogin, setupPassword, cancelAuth, logout,
  }
}
