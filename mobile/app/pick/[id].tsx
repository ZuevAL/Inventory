import { useLocalSearchParams, useRouter } from 'expo-router';
import { OperationForm } from '../../src/operation-form';
import { SnapshotState } from '../../src/snapshot-state';
import { Empty, Page, SectionTitle } from '../../src/ui';
import { useWarehouseContext } from '../../src/warehouse-context';

export default function Pick() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { snapshot } = useWarehouseContext();
  const order = snapshot?.orders.find(order => order.lines.some(line => line.id === Number(id)));
  const line = order?.lines.find(line => line.id === Number(id));
  const back = () => {
    if (router.canGoBack()) router.back();
    else if (order) router.replace({ pathname: '/orders/[id]', params: { id: String(order.id) } });
    else router.replace('/orders');
  };

  return (
    <Page active="orders">
      <SectionTitle title="Сборка позиции" description={order ? `Заказ ${order.number}` : undefined} back={back} />
      {!snapshot ? <SnapshotState /> : order && line
        ? <OperationForm snapshot={snapshot} selection={{ order, line }} onDone={back} />
        : <Empty title="Позиция не найдена" />}
    </Page>
  );
}
