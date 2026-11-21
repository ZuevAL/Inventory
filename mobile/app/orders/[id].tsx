import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { orderProgress, shelfLocations } from '../../src/orders';
import { SnapshotState } from '../../src/snapshot-state';
import { Badge, Button, Empty, IconTile, Notice, Page, SectionTitle, styles, theme } from '../../src/ui';
import { useWarehouseContext } from '../../src/warehouse-context';

export default function OrderDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { snapshot } = useWarehouseContext();
  const order = snapshot?.orders.find(item => item.id === Number(id));
  const back = () => router.canGoBack() ? router.back() : router.replace('/orders');
  const progress = order ? orderProgress(order) : { quantity: 0, picked: 0 };
  const percent = progress.quantity > 0 ? Math.round(progress.picked / progress.quantity * 100) : 0;
  const lines = snapshot && order ? order.lines.map(line => ({
    line,
    product: snapshot.products.find(product => product.id === line.product_id),
    locations: shelfLocations(snapshot, line.product_id),
  })).sort((left, right) => {
    const leftDone = left.line.picked >= left.line.quantity;
    const rightDone = right.line.picked >= right.line.quantity;
    return Number(leftDone) - Number(rightDone)
      || Number(!left.locations.length) - Number(!right.locations.length)
      || (left.locations[0]?.shelf.code ?? '').localeCompare(right.locations[0]?.shelf.code ?? '', 'ru', { numeric: true })
      || left.line.id - right.line.id;
  }) : [];

  return (
    <Page active="orders">
      <SectionTitle title={order ? `Заказ ${order.number}` : 'Заказ'} description={order?.customer || undefined} back={back} />
      {!snapshot ? <SnapshotState /> : !order ? <Empty title="Заказ не найден" icon="clipboard-outline" /> : (
        <>
          <View style={styles.card}>
            <View style={styles.between}>
              <Text style={styles.body}>Собрано {progress.picked} из {progress.quantity} шт.</Text>
              {progress.picked >= progress.quantity && progress.quantity > 0 && <Badge tone="good" icon="checkmark-outline">Собран</Badge>}
            </View>
            <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: percent }} style={detail.track}>
              <View style={[detail.fill, { width: `${percent}%` }]} />
            </View>
          </View>
          <View style={styles.stack}>
            <Text accessibilityRole="header" style={styles.heading}>Позиции заказа</Text>
            {!lines.length && <Empty title="В заказе нет позиций" />}
            {lines.map(({ line, product, locations }) => {
              const done = line.picked >= line.quantity;
              return (
                <View style={styles.card} key={line.id}>
                  <View style={styles.row}>
                    <IconTile icon={done ? 'checkmark-outline' : 'cube-outline'} />
                    <View style={styles.stretch}>
                      <Text style={styles.body}>{product?.name ?? 'Товар'}</Text>
                      <Text style={styles.caption}>Собрано {line.picked} из {line.quantity} шт.</Text>
                    </View>
                  </View>
                  {!done && (
                    <>
                      {locations.length > 0
                        ? <View style={detail.locations}>{locations.map(({ shelf, quantity }) => (
                            <Badge key={shelf.id} icon="location-outline">{shelf.code} · {quantity} шт.</Badge>
                          ))}</View>
                        : <Notice text="На полках нет остатка этого товара." tone="warning" />}
                      <Button
                        label="Собрать позицию"
                        icon="scan-outline"
                        disabled={!locations.length || !product}
                        onPress={() => router.push({ pathname: '/pick/[id]', params: { id: String(line.id) } })}
                      />
                    </>
                  )}
                </View>
              );
            })}
          </View>
        </>
      )}
    </Page>
  );
}

const detail = StyleSheet.create({
  track: { height: 9, borderRadius: 8, backgroundColor: theme.pale, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: theme.green },
  locations: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
});
