import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { orderProgress } from '../../src/orders';
import { SnapshotState } from '../../src/snapshot-state';
import { Badge, Empty, Field, ListLink, Page, SectionTitle, styles, theme } from '../../src/ui';
import { useWarehouseContext } from '../../src/warehouse-context';

export default function Orders() {
  const router = useRouter();
  const { snapshot } = useWarehouseContext();
  const [query, setQuery] = useState('');
  const [complete, setComplete] = useState(false);
  const normalized = query.trim().toLocaleLowerCase('ru');
  const rows = snapshot?.orders.map(order => ({ order, ...orderProgress(order) }))
    .filter(({ order, picked, quantity }) =>
      (picked >= quantity) === complete &&
      (!normalized || `${order.number} ${order.customer}`.toLocaleLowerCase('ru').includes(normalized)),
    ) ?? [];

  return (
    <Page active="orders">
      <SectionTitle title="Заказы" description="Выберите заказ и позицию для сборки." />
      {!snapshot ? <SnapshotState /> : (
        <View style={styles.stack}>
          <View style={orderStyles.filters}>
            {[false, true].map(done => (
              <Pressable
                key={String(done)}
                accessibilityRole="tab"
                accessibilityState={{ selected: complete === done }}
                onPress={() => setComplete(done)}
                style={[orderStyles.filter, complete === done && orderStyles.filterSelected]}
              >
                <Text style={[styles.body, complete === done && orderStyles.selectedText]}>{done ? 'Собранные' : 'К сборке'}</Text>
              </Pressable>
            ))}
          </View>
          <Field label="Поиск заказа" value={query} onChangeText={setQuery} placeholder="Номер или получатель" autoCapitalize="none" />
          {rows.length ? (
            <View style={orderStyles.list}>
              {rows.map(({ order, picked, quantity }, index) => (
                <ListLink
                  key={order.id}
                  icon="clipboard-outline"
                  title={order.number}
                  detail={order.customer || undefined}
                  right={<Badge tone={complete ? 'good' : 'neutral'}>{picked} / {quantity} шт.</Badge>}
                  last={index === rows.length - 1}
                  onPress={() => router.push({ pathname: '/orders/[id]', params: { id: String(order.id) } })}
                />
              ))}
            </View>
          ) : <Empty title={normalized ? 'Заказы не найдены' : complete ? 'Нет собранных заказов' : 'Нет заказов к сборке'} icon="clipboard-outline" />}
        </View>
      )}
    </Page>
  );
}

const orderStyles = StyleSheet.create({
  filters: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  filter: { paddingHorizontal: 15, minHeight: 43, justifyContent: 'center', borderColor: theme.line, borderWidth: 1, borderRadius: 22, backgroundColor: 'white' },
  filterSelected: { borderColor: theme.dark, backgroundColor: theme.dark },
  selectedText: { color: 'white' },
  list: { borderRadius: 15, borderWidth: 1, borderColor: theme.line, backgroundColor: 'white', overflow: 'hidden' },
});
