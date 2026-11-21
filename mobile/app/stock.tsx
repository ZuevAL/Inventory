import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SnapshotState } from '../src/snapshot-state';
import { Badge, Empty, Field, IconTile, Page, SectionTitle, styles, theme } from '../src/ui';
import type { Product, Shelf } from '../src/warehouse-model';
import { useWarehouseContext } from '../src/warehouse-context';

export default function Stock() {
  const { snapshot } = useWarehouseContext();
  const [search, setSearch] = useState('');
  const query = search.trim().toLocaleLowerCase('ru');
  const products = new Map(snapshot?.products.map(product => [product.id, product]));
  const shelves = new Map(snapshot?.shelves.map(shelf => [shelf.id, shelf]));
  const rowsByShelf = new Map<number, { shelf: Shelf; products: { product: Product; quantity: number }[] }>();
  for (const stock of snapshot?.stock ?? []) {
    const product = products.get(stock.product_id);
    const shelf = shelves.get(stock.shelf_id);
    if (!product || !shelf || stock.quantity <= 0) continue;

    const text = [shelf.code, shelf.zone, product.name, product.sku, ...product.barcodes].join(' ').toLocaleLowerCase('ru');
    if (query && !text.includes(query)) continue;

    const row = rowsByShelf.get(shelf.id) ?? { shelf, products: [] };
    row.products.push({ product, quantity: stock.quantity });
    rowsByShelf.set(shelf.id, row);
  }
  const rows = [...rowsByShelf.values()].sort((left, right) => left.shelf.code.localeCompare(right.shelf.code, 'ru', { numeric: true }));
  rows.forEach(row => row.products.sort((left, right) => left.product.name.localeCompare(right.product.name, 'ru')));

  return (
    <Page active="stock">
      <SectionTitle title="Остатки" description="Товары и количество по полкам." />
      {!snapshot ? <SnapshotState /> : (
        <>
          <Field label="Поиск товара или полки" placeholder="Название, штрихкод или код полки" value={search} onChangeText={setSearch} autoCapitalize="none" />
          {rows.length ? rows.map(({ shelf, products }) => (
            <View style={styles.card} key={shelf.id}>
              <View style={styles.row}>
                <IconTile icon="location-outline" />
                <View style={styles.stretch}>
                  <Text style={styles.heading}>{shelf.code}</Text>
                  {shelf.zone && <Text style={styles.caption}>{shelf.zone}</Text>}
                </View>
              </View>
              <View style={stockStyles.items}>
                {products.map(({ product, quantity }) => (
                  <View key={product.id} style={stockStyles.item}>
                    <View style={styles.stretch}>
                      <Text style={styles.body}>{product.name}</Text>
                      <Text style={styles.caption}>{product.sku || product.barcodes[0]}</Text>
                    </View>
                    <Badge>{quantity} шт.</Badge>
                  </View>
                ))}
              </View>
            </View>
          )) : <Empty title={query ? 'По запросу ничего не найдено' : 'На полках пока нет товаров'} icon="layers-outline" />}
        </>
      )}
    </Page>
  );
}

const stockStyles = StyleSheet.create({
  items: { marginTop: 1 },
  item: { ...styles.between, paddingVertical: 11, borderTopColor: theme.line, borderTopWidth: 1 },
});
