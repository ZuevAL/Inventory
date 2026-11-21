import { useState } from 'react';
import { Busy, Button, Empty, Notice, styles } from './ui';
import { View } from 'react-native';
import { useWarehouseContext } from './warehouse-context';

export function SnapshotState() {
  const { loading, error, sync } = useWarehouseContext();
  const [refreshing, setRefreshing] = useState(false);

  if (loading) return <Busy />;
  return (
    <View style={styles.stack}>
      <Empty title="Данные склада недоступны" icon="cloud-offline-outline" message="Подключитесь к серверу, чтобы загрузить товары, полки и заказы." />
      {error && <Notice text={error} tone="danger" />}
      <Button label="Загрузить данные" icon="refresh-outline" busy={refreshing} onPress={() => {
        setRefreshing(true);
        void sync().catch(() => {}).finally(() => setRefreshing(false));
      }} />
    </View>
  );
}
