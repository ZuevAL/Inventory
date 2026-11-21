export type Product = { id: number; name: string; barcodes: string[]; sku?: string }
export type Shelf = { id: number; code: string; qr: string; zone?: string }
export type Stock = { product_id: number; shelf_id: number; quantity: number }
export type OrderLine = { id: number; product_id: number; quantity: number; picked: number }
export type Order = { id: number; number: string; customer: string; lines: OrderLine[] }

export type OperationInput = {
  kind: 'putaway' | 'pick'
  product_code: string
  shelf_code: string
  quantity: number
  order_line_id?: number
}

export type Operation = {
  operation_id: string
  kind: OperationInput['kind']
  product_id: number
  shelf_id: number
  quantity: number
  order_line_id: number | null
  created_at: string
  user_id: number
  product_name?: string
  shelf_label?: string
}

export type PendingOperation = OperationInput & {
  operation_id: string
  status: 'queued' | 'conflict'
  error: string | null
}

export type Snapshot = {
  products: Product[]
  shelves: Shelf[]
  stock: Stock[]
  orders: Order[]
  operations: Operation[]
}

export type CachedWarehouse = { snapshot: Snapshot | null; pending: PendingOperation[] }

export type User = {
  id: number
  login: string
  full_name: string
  role: 'admin' | 'worker'
  must_change_password: boolean
  recovery_required: boolean
}

export type StoredSession = {
  refreshToken: string
  expiresAt: number
  user: User
  url: string
  refreshUncertain?: boolean
}

export function findShelf(shelves: Shelf[], code: string): Shelf | undefined {
  const scanned = code.trim()
  return shelves.find(shelf => shelf.qr === scanned) ??
    shelves.find(shelf => shelf.code === scanned)
}

export function findProduct(products: Product[], code: string): Product | undefined {
  const scanned = code.trim()
  const product = products.find(item => item.barcodes.includes(scanned))
  if (product) return product
  // Scanners can report UPC-A as an EAN-13 with a leading zero.
  if (/^0\d{12}$/.test(scanned)) {
    return products.find(item => item.barcodes.includes(scanned.slice(1)))
  }
  if (/^\d{12}$/.test(scanned)) {
    return products.find(item => item.barcodes.includes('0' + scanned))
  }
}

function resolveOperation(snapshot: Snapshot, input: OperationInput) {
  if (!Number.isInteger(input.quantity) || input.quantity < 1 || input.quantity > 100_000) {
    throw new Error('Введите целое количество от 1 до 100 000')
  }
  const product = findProduct(snapshot.products, input.product_code)
  if (!product) throw new Error('Товар с таким штрихкодом не найден')
  const shelf = findShelf(snapshot.shelves, input.shelf_code)
  if (!shelf) throw new Error('Полка с таким кодом не найдена')
  const stock = snapshot.stock.find(item => item.product_id === product.id && item.shelf_id === shelf.id)
  const order = snapshot.orders.find(item => item.lines.some(line => line.id === input.order_line_id))
  const line = order?.lines.find(item => item.id === input.order_line_id)
  if (input.kind === 'pick') {
    if (!line || line.product_id !== product.id) throw new Error('Товар не совпадает с позицией заказа')
    if (line.quantity - line.picked < input.quantity) throw new Error('Количество превышает остаток по заказу')
    if ((stock?.quantity ?? 0) < input.quantity) throw new Error('На выбранной полке недостаточно товара')
  }
  return { product, shelf, stock, order, line }
}

export function validatedInput(snapshot: Snapshot, input: OperationInput): OperationInput {
  const { product, shelf } = resolveOperation(snapshot, input)
  return {
    ...input,
    product_code: product.barcodes.find(code => code === input.product_code.trim()) ?? product.barcodes[0],
    shelf_code: shelf.qr,
  }
}

export function projectSnapshot(warehouse: CachedWarehouse): Snapshot | null {
  let snapshot = warehouse.snapshot
  if (!snapshot) return null

  const appliedIds = new Set(snapshot.operations.map(operation => operation.operation_id))
  for (const operation of warehouse.pending) {
    if (operation.status !== 'queued' || appliedIds.has(operation.operation_id)) continue
    try {
      const { product, shelf, stock, order, line } = resolveOperation(snapshot, operation)
      const quantity = (stock?.quantity ?? 0) + (
        operation.kind === 'putaway' ? operation.quantity : -operation.quantity
      )
      const nextStock = { product_id: product.id, shelf_id: shelf.id, quantity }
      snapshot = {
        ...snapshot,
        stock: stock
          ? snapshot.stock.map(item => item === stock ? nextStock : item)
          : [...snapshot.stock, nextStock],
        orders: operation.kind === 'pick' && order && line
          ? snapshot.orders.map(item => item === order ? {
            ...order,
            lines: order.lines.map(item => item === line ? { ...line, picked: line.picked + operation.quantity } : item),
          } : item)
          : snapshot.orders,
      }
    } catch {
      // A dependent queued operation may become inapplicable after a server conflict.
      // The outbox still submits it and displays the server's response.
    }
  }
  return snapshot
}
