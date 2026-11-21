import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { findProduct, findShelf } from '../src/warehouse-model';
import { Badge, Button, Empty, ListLink, Notice, Page, SectionTitle, styles, theme } from '../src/ui';
import { useWarehouseContext } from '../src/warehouse-context';

export default function Activity() {
  const router = useRouter();
  const { snapshot, pending, online, error, sync, discard } = useWarehouseContext();
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState('');
  const [actionError, setActionError] = useState('');
  const history = snapshot?.operations ?? [];

  async function synchronize() {
    setActionError('');
    setBusy(true);
    try {
      await sync();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Не удалось обновить данные');
    } finally {
      setBusy(false);
    }
  }

  async function discardSelected() {
    setBusy(true);
    setActionError('');
    try {
      await discard(selected);
      setSelected('');
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Не удалось удалить операцию');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page active="home">
      <SectionTitle title="Журнал операций" back={() => router.canGoBack() ? router.back() : router.replace('/')} />
      <View style={styles.card}>
        <View style={styles.between}>
          <Text style={styles.heading}>Синхронизация</Text>
          <Badge tone={online ? 'good' : 'warning'} icon={online ? 'cloud-done-outline' : 'cloud-offline-outline'}>{online ? 'Сервер доступен' : 'Офлайн'}</Badge>
        </View>
        {!online && <Text style={styles.caption}>Новые операции сохраняются на устройстве и отправляются при восстановлении связи.</Text>}
        {pending.length > 0 && <Text style={styles.caption}>Операций на устройстве: {pending.length}.</Text>}
        <Button label="Синхронизировать" icon="refresh-outline" busy={busy && !selected} disabled={!!selected} onPress={() => void synchronize()} />
        {(actionError || error) && <Notice text={actionError || error || ''} tone="danger" />}
      </View>
      {pending.length > 0 && (
        <View style={styles.stack}>
          <Text accessibilityRole="header" style={styles.heading}>Операции на устройстве</Text>
          {pending.map(operation => {
            const productName = findProduct(snapshot?.products ?? [], operation.product_code)?.name ?? operation.product_code;
            const shelfLabel = findShelf(snapshot?.shelves ?? [], operation.shelf_code)?.code ?? operation.shelf_code;
            const conflict = operation.status === 'conflict';
            return (
              <View style={styles.card} key={operation.operation_id}>
                <View style={styles.between}>
                  <Text style={[styles.body, styles.stretch]}>{operation.kind === 'putaway' ? 'Раскладка' : 'Сборка'}</Text>
                  <Badge tone={conflict ? 'danger' : 'warning'}>{conflict ? 'Конфликт' : 'В очереди'}</Badge>
                </View>
                <Text style={styles.caption}>{productName} · {shelfLabel} · {operation.quantity} шт.</Text>
                {operation.error && <Notice tone="danger" text={operation.error} />}
                {conflict && (selected === operation.operation_id ? (
                  <>
                    <Notice text="Операция отклонена сервером. Удалить запись с устройства?" tone="warning" />
                    <View style={styles.row}>
                      <Button label="Отмена" variant="secondary" style={styles.stretch} disabled={busy} onPress={() => setSelected('')} />
                      <Button label="Удалить" variant="danger" style={styles.stretch} busy={busy} onPress={() => void discardSelected()} />
                    </View>
                  </>
                ) : <Button label="Удалить отклонённую операцию" variant="danger" disabled={busy} onPress={() => setSelected(operation.operation_id)} />)}
              </View>
            );
          })}
        </View>
      )}
      <View style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>Подтверждённые операции</Text>
        {history.length ? (
          <View style={activity.list}>
            {history.map((item, index) => {
              const product = item.product_name || snapshot?.products.find(product => product.id === item.product_id)?.name || 'Товар';
              const shelf = item.shelf_label || snapshot?.shelves.find(shelf => shelf.id === item.shelf_id)?.code || 'Полка';
              const date = new Date(item.created_at);
              const when = Number.isNaN(date.getTime()) ? ''
                : date.toLocaleString('ru-RU', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
              return (
                <ListLink
                  key={item.operation_id}
                  icon={item.kind === 'putaway' ? 'cube-outline' : 'remove-circle-outline'}
                  title={product}
                  detail={`${item.kind === 'putaway' ? 'Раскладка' : 'Сборка'} · ${shelf}${when ? ` · ${when}` : ''}`}
                  right={<Badge tone={item.kind === 'putaway' ? 'good' : 'neutral'}>{item.kind === 'putaway' ? '+' : '−'}{item.quantity} шт.</Badge>}
                  last={index === history.length - 1}
                />
              );
            })}
          </View>
        ) : <Empty title="Операций пока нет" icon="time-outline" />}
      </View>
    </Page>
  );
}

const activity = StyleSheet.create({
  list: { borderRadius: 15, borderWidth: 1, borderColor: theme.line, backgroundColor: 'white', overflow: 'hidden' },
});
