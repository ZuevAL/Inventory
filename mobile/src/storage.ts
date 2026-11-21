import * as Crypto from 'expo-crypto'
import * as SecureStore from 'expo-secure-store'
import { openDatabaseAsync } from 'expo-sqlite'

import type { CachedWarehouse, StoredSession } from './warehouse-model'

let connection: ReturnType<typeof openDatabaseAsync> | undefined

function database() {
  connection ??= openDatabaseAsync('inventory-mobile.db').then(async db => {
    await db.execAsync('CREATE TABLE IF NOT EXISTS local_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return db
  }).catch(error => {
    connection = undefined
    throw error
  })
  return connection
}

export async function readLocal<T>(key: string): Promise<T | null> {
  const row = await (await database()).getFirstAsync<{ value: string }>(
    'SELECT value FROM local_state WHERE key = ?', key,
  )
  return row ? JSON.parse(row.value) as T : null
}

export async function writeLocal(key: string, value: string | CachedWarehouse): Promise<void> {
  await (await database()).runAsync(
    'INSERT INTO local_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
    key, JSON.stringify(value),
  )
}

const sessionKey = 'inventory-session'
const secureOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }

export async function readSession(): Promise<StoredSession | null> {
  const value = await SecureStore.getItemAsync(sessionKey, secureOptions)
  return value ? JSON.parse(value) as StoredSession : null
}

export async function writeSession(session: StoredSession | null): Promise<void> {
  if (session) await SecureStore.setItemAsync(sessionKey, JSON.stringify(session), secureOptions)
  else await SecureStore.deleteItemAsync(sessionKey, secureOptions)
}

export const operationId = Crypto.randomUUID
