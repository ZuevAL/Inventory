import type { Order, Snapshot } from './warehouse-model';

export function orderProgress(order: Order) {
  return order.lines.reduce(
    ({ quantity, picked }, line) => ({ quantity: quantity + line.quantity, picked: picked + line.picked }),
    { quantity: 0, picked: 0 },
  );
}

export function shelfLocations(snapshot: Snapshot, productId: number) {
  const shelves = new Map(snapshot.shelves.map(shelf => [shelf.id, shelf]));
  return snapshot.stock.flatMap(stock => {
    if (stock.product_id !== productId || stock.quantity <= 0) return [];
    const shelf = shelves.get(stock.shelf_id);
    return shelf ? [{ shelf, quantity: stock.quantity }] : [];
  }).sort((left, right) => left.shelf.code.localeCompare(right.shelf.code, 'ru', { numeric: true }));
}
