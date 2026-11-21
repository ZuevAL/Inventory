import { OperationForm } from '../src/operation-form';
import { SnapshotState } from '../src/snapshot-state';
import { Page, SectionTitle } from '../src/ui';
import { useWarehouseContext } from '../src/warehouse-context';

export default function Putaway() {
  const { snapshot } = useWarehouseContext();
  return (
    <Page active="putaway">
      <SectionTitle title="Раскладка" description="Отсканируйте товар и QR-код полки, затем подтвердите количество." />
      {snapshot ? <OperationForm snapshot={snapshot} /> : <SnapshotState />}
    </Page>
  );
}
