const assert = require('node:assert/strict');
const test = require('node:test');

const { findProduct, findShelf, projectSnapshot, validatedInput } = require('../mobile/src/warehouse-model.ts');

const UPC = '036000291452';
const EAN = `0${UPC}`;
const CATALOG = {
  products: [{ id: 1, name: 'Кабель', barcodes: [UPC] }],
  shelves: [
    { id: 1, code: 'A-01-01', qr: 'shelf:1' },
    { id: 2, code: 'A-01-02', qr: 'shelf:2' },
  ],
  stock: [{ product_id: 1, shelf_id: 1, quantity: 3 }],
  orders: [{
    id: 1, number: '1042', customer: 'Магазин',
    lines: [{ id: 1, product_id: 1, quantity: 4, picked: 0 }],
  }],
  operations: [],
};

const PUTAWAY = { kind: 'putaway', product_code: UPC, shelf_code: 'shelf:2', quantity: 4 };
const PICK = { kind: 'pick', product_code: UPC, shelf_code: 'shelf:2', quantity: 2, order_line_id: 1 };

function pending(operation, id, status = 'queued', error = null) {
  return { ...operation, operation_id: id, status, error };
}

test('offline projection adds new stock and lets a following pick use it', () => {
  const cached = { snapshot: structuredClone(CATALOG), pending: [pending(PUTAWAY, 'first'), pending(PICK, 'second')] };
  const after = projectSnapshot(cached);
  assert.deepEqual(after.stock, [
    { product_id: 1, shelf_id: 1, quantity: 3 },
    { product_id: 1, shelf_id: 2, quantity: 2 },
  ]);
  assert.equal(after.orders[0].lines[0].picked, 2);
  assert.deepEqual(cached.snapshot, CATALOG);
  assert.equal(cached.pending.length, 2);
});

test('conflict and its now-invalid dependent pick remain in the queue without altering stock', () => {
  const putaway = pending(PUTAWAY, 'first', 'conflict', 'Товар отсутствует');
  const pick = pending(PICK, 'second');
  const cached = { snapshot: CATALOG, pending: [putaway, pick] };
  assert.deepEqual(projectSnapshot(cached), CATALOG);
  assert.deepEqual(cached.pending, [putaway, pick]);
});

test('projection skips pending IDs already committed in the server snapshot', () => {
  const snapshot = {
    ...CATALOG,
    stock: [...CATALOG.stock, { product_id: 1, shelf_id: 2, quantity: 4 }],
    operations: [{ operation_id: 'committed' }],
  };
  const after = projectSnapshot({
    snapshot, pending: [pending(PUTAWAY, 'committed'), pending(PICK, 'still-queued')],
  });
  assert.equal(after.stock[1].quantity, 2);
  assert.equal(after.orders[0].lines[0].picked, 2);
});

test('queued pick from an empty shelf fails even when the same product is stocked elsewhere', () => {
  assert.throws(() => validatedInput(CATALOG, PICK), /на выбранной полке/i);
  assert.throws(() => validatedInput(CATALOG, { ...PICK, shelf_code: 'shelf:1', order_line_id: 99 }), /позицией заказа/i);
});

test('scanned UPC and EAN aliases use the catalog barcode and the immutable shelf QR', () => {
  assert.deepEqual(validatedInput(CATALOG, {
    ...PUTAWAY, product_code: ` ${EAN}\n`, shelf_code: ' A-01-02 ',
  }), PUTAWAY);

  const eanProduct = { id: 2, name: 'EAN', barcodes: [EAN] };
  assert.equal(findProduct([eanProduct], UPC), eanProduct);
  assert.equal(findProduct([CATALOG.products[0], eanProduct], EAN), eanProduct);
  assert.equal(findProduct([eanProduct], 'unknown'), undefined);
});

test('shelf QR takes precedence over a coinciding display code', () => {
  const collision = { id: 3, code: 'shelf:2', qr: 'shelf:3' };
  const shelves = [collision, ...CATALOG.shelves];
  assert.equal(findShelf(shelves, ' shelf:2 '), CATALOG.shelves[1]);
  assert.deepEqual(validatedInput({ ...CATALOG, shelves }, PUTAWAY), PUTAWAY);
});

test('queued operations need a downloaded snapshot before projection', () => {
  assert.equal(projectSnapshot({ snapshot: null, pending: [pending(PUTAWAY, 'first')] }), null);
});
