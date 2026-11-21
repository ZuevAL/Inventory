import type { CachedWarehouse, StoredSession } from './warehouse-model'

const prefix = 'inventory:'
let session: StoredSession | null = null

export async function readLocal<T>(key: string): Promise<T | null> {
  const value = window.localStorage.getItem(prefix + key)
  return value ? JSON.parse(value) as T : null
}

export async function writeLocal(key: string, value: string | CachedWarehouse): Promise<void> {
  window.localStorage.setItem(prefix + key, JSON.stringify(value))
}

export async function readSession(): Promise<StoredSession | null> {
  return session
}

export async function writeSession(value: StoredSession | null): Promise<void> {
  session = value
}

export function operationId(): string {
  return window.crypto.randomUUID()
}
