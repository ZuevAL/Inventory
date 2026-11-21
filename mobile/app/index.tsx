import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { orderProgress } from '../src/orders';
import { SnapshotState } from '../src/snapshot-state';
import { Badge, Button, Empty, IconTile, ListLink, Page, SectionTitle, styles, theme, type IconName } from '../src/ui';
import { useWarehouseContext } from '../src/warehouse-context';

const bars = [4, 7, 3, 3, 6, 4, 7, 4, 3, 6, 3, 3, 7, 4, 3, 5, 3];

export default function Overview() {
  const { snapshot, session } = useWarehouseContext();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const orders = snapshot?.orders.filter(order => {
    const progress = orderProgress(order);
    return progress.picked < progress.quantity;
  }) ?? [];
  const stockUnits = snapshot?.stock.reduce((total, stock) => total + stock.quantity, 0);

  return (
    <Page active="home">
      <SectionTitle title="Рабочий стол" description={session?.user.full_name} />
      {snapshot ? (
        <>
          <View style={[dashboard.actions, width >= 680 && dashboard.actionsWide]}>
            <Pressable accessibilityRole="button" accessibilityLabel="Начать раскладку" onPress={() => router.push('/putaway')} style={({ pressed }) => [dashboard.hero, pressed && dashboard.pressed]}>
              <View style={dashboard.heroText}>
                <View style={dashboard.heroIcon}><Ionicons color={theme.accent} name="scan-outline" size={22} /></View>
                <Text style={dashboard.heroTitle}>Раскладка товара</Text>
                <Text style={dashboard.heroDescription}>Штрихкод товара → QR-код полки</Text>
                <View style={dashboard.heroButton}>
                  <Text style={dashboard.heroButtonText}>Начать раскладку</Text>
                  <Ionicons color={theme.dark} size={17} name="arrow-forward" />
                </View>
              </View>
              <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={dashboard.scanArt}>
                <View style={dashboard.scanFrame}>
                  <View style={[dashboard.bracket, dashboard.topLeft]} />
                  <View style={[dashboard.bracket, dashboard.topRight]} />
                  <View style={[dashboard.bracket, dashboard.bottomLeft]} />
                  <View style={[dashboard.bracket, dashboard.bottomRight]} />
                  {bars.map((bar, i) => <View key={i} style={[dashboard.bar, { width: bar }]} />)}
                  <View style={dashboard.scanLine} />
                </View>
              </View>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Открыть заказы" onPress={() => router.push('/orders')} style={({ pressed }) => [styles.card, dashboard.pick, pressed && dashboard.pressed]}>
              <View style={styles.between}>
                <IconTile icon="clipboard-outline" color="blue" />
                <Badge tone="good">{orders.length} к сборке</Badge>
              </View>
              <View style={styles.between}>
                <View style={styles.stretch}>
                  <Text style={dashboard.pickTitle}>Сборка заказов</Text>
                  <Text style={styles.caption}>Найдите товар на полке и подтвердите сборку.</Text>
                </View>
                <Ionicons name="arrow-forward-outline" color={theme.green} size={21} />
              </View>
            </Pressable>
          </View>
          <View style={dashboard.metrics}>
            <Metric icon="cube-outline" label="Товары" value={snapshot.products.length} />
            <Metric icon="location-outline" label="Полки" value={snapshot.shelves.length} />
            <Metric icon="layers-outline" label="Штук в наличии" value={stockUnits ?? 0} />
          </View>
          <View style={styles.stack}>
            <View style={styles.between}>
              <Text accessibilityRole="header" style={styles.heading}>Заказы к сборке</Text>
              <Pressable accessibilityRole="button" onPress={() => router.push('/orders')} style={dashboard.allOrders}>
                <Text style={dashboard.link}>Все заказы</Text>
                <Ionicons name="arrow-forward" size={15} color={theme.green} />
              </Pressable>
            </View>
            {orders.length > 0 ? (
              <View style={dashboard.list}>
                {orders.slice(0, 4).map((order, index, items) => {
                  const progress = orderProgress(order);
                  return (
                    <ListLink
                      key={order.id}
                      icon="clipboard-outline"
                      title={order.number}
                      detail={order.customer || undefined}
                      right={<Badge>{progress.picked} / {progress.quantity} шт.</Badge>}
                      last={index === items.length - 1}
                      onPress={() => router.push({ pathname: '/orders/[id]', params: { id: String(order.id) } })}
                    />
                  );
                })}
              </View>
            ) : <Empty title="Нет заказов к сборке" icon="clipboard-outline" />}
          </View>
          <Button label="Журнал операций" icon="time-outline" variant="secondary" onPress={() => router.push('/activity')} />
        </>
      ) : <SnapshotState />}
    </Page>
  );
}

function Metric({ icon, label, value }: { icon: IconName; label: string; value: number }) {
  return (
    <View style={dashboard.metric}>
      <Ionicons name={icon} size={17} color={theme.green} />
      <Text style={dashboard.metricNumber}>{value.toLocaleString('ru-RU')}</Text>
      <Text style={dashboard.metricLabel}>{label}</Text>
    </View>
  );
}

const dashboard = StyleSheet.create({
  actions: { gap: 12 },
  actionsWide: { flexDirection: 'row', alignItems: 'stretch' },
  hero: { flex: 1.7, minHeight: 195, overflow: 'hidden', borderRadius: 19, backgroundColor: theme.dark, padding: 20, justifyContent: 'center' },
  heroText: { position: 'relative', zIndex: 1, alignItems: 'flex-start' },
  heroIcon: { padding: 8, borderRadius: 11, backgroundColor: '#294342' },
  heroTitle: { marginTop: 10, color: '#FFFFFF', fontSize: 23, fontWeight: '800', letterSpacing: -0.55 },
  heroDescription: { marginTop: 3, color: '#D1DDD6', fontSize: 13, fontWeight: '500' },
  heroButton: { marginTop: 15, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9, backgroundColor: theme.accent, flexDirection: 'row', alignItems: 'center', gap: 6 },
  heroButtonText: { color: theme.dark, fontSize: 12, fontWeight: '800' },
  scanArt: { position: 'absolute', right: -9, top: -13, width: 204, height: 204, borderRadius: 102, backgroundColor: '#173738', alignItems: 'center', justifyContent: 'center', opacity: 0.64 },
  scanFrame: { position: 'relative', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 3, width: 153, height: 100, borderRadius: 15, backgroundColor: '#1F4141', transform: [{ rotate: '-13deg' }] },
  bar: { backgroundColor: '#6E9E8C', height: 52, borderRadius: 1 },
  scanLine: { height: 2, width: '105%', position: 'absolute', top: 49, backgroundColor: '#9DE97D', opacity: 0.85 },
  bracket: { position: 'absolute', width: 16, height: 16, borderColor: '#9DE97D' },
  topLeft: { top: 7, left: 7, borderTopWidth: 2, borderLeftWidth: 2, borderTopLeftRadius: 3 },
  topRight: { top: 7, right: 7, borderTopWidth: 2, borderRightWidth: 2, borderTopRightRadius: 3 },
  bottomLeft: { bottom: 7, left: 7, borderBottomWidth: 2, borderLeftWidth: 2, borderBottomLeftRadius: 3 },
  bottomRight: { bottom: 7, right: 7, borderBottomWidth: 2, borderRightWidth: 2, borderBottomRightRadius: 3 },
  pick: { flex: 1, alignItems: 'stretch', justifyContent: 'space-between', gap: 12 },
  pickTitle: { color: theme.ink, fontSize: 22, fontWeight: '800', marginBottom: 4, letterSpacing: -0.45 },
  pressed: { opacity: 0.8 },
  metrics: { backgroundColor: theme.surface, flexDirection: 'row', flexWrap: 'wrap', borderRadius: 15, borderColor: theme.line, borderWidth: 1, overflow: 'hidden' },
  metric: { flex: 1, gap: 4, padding: 12, minWidth: 86 },
  metricNumber: { color: theme.ink, fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
  metricLabel: { color: theme.secondary, fontSize: 12, fontWeight: '600' },
  list: { borderRadius: 15, borderWidth: 1, borderColor: theme.line, backgroundColor: 'white', overflow: 'hidden' },
  allOrders: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 4 },
  link: { color: theme.green, fontSize: 13, fontWeight: '800' },
});
