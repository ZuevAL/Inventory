import * as Haptics from 'expo-haptics';
import { useState, useEffect, useRef } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { type OrderLine, type Order, type Product, type Shelf, type Snapshot, findProduct, findShelf } from './warehouse-model';
import { useWarehouseContext } from './warehouse-context';
import { shelfLocations } from './orders';
import { ScanField } from './scan-field';
import { Badge, Button, Empty, Field, Notice, styles, theme } from './ui';

type Selection = { order: Order; line: OrderLine };
type Scan<T> = { code: string; item: T };

export function OperationForm({ snapshot, selection, onDone }: { snapshot: Snapshot; selection?: Selection; onDone?: () => void }) {
  const { submit } = useWarehouseContext();
  const [product, setProduct] = useState<Scan<Product> | null>(null);
  const [shelf, setShelf] = useState<Scan<Shelf> | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');
  const [queued, setQueued] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const formBusy = useRef(false);
  const lastSelection = useRef(selection?.line.id);
  const expected = snapshot.products.find(item => item.id === selection?.line.product_id);
  const orderedQty = selection ? selection.line.quantity - selection.line.picked : null;
  const locations = expected ? shelfLocations(snapshot, expected.id) : [];
  const available = product && shelf
    ? snapshot.stock.find(item => item.product_id === product.item.id && item.shelf_id === shelf.item.id)?.quantity ?? 0
    : 0;
  const limit = selection ? Math.min(orderedQty ?? 0, available, 100_000) : 100_000;
  const entered = /^\d+$/.test(quantity) ? Number(quantity) : NaN;
  const validQuantity = Number.isInteger(entered) && entered > 0 && entered <= limit;

  useEffect(() => {
    const id = selection?.line.id;
    if (lastSelection.current === id) return;
    lastSelection.current = id;
    setProduct(null);
    setShelf(null);
    setQuantity('1');
    setError('');
    setResult('');
  }, [selection?.line.id]);

  function startAgain() {
    setProduct(null);
    setShelf(null);
    setQuantity('1');
    setResult('');
    setError('');
    setAttempt(value => value + 1);
  }

  function onProduct(code: string) {
    const found = findProduct(snapshot.products, code);
    if (!found) {
      setError('Товар с таким штрихкодом не найден');
      return;
    }
    if (selection && found.id !== selection.line.product_id) {
      setError(`Отсканирован другой товар. Нужен «${expected?.name ?? 'товар из заказа'}».`);
      return;
    }
    setError('');
    setProduct({ code, item: found });
    if (Platform.OS !== 'web') void Haptics.selectionAsync().catch(() => {});
  }

  function onShelf(code: string) {
    const found = findShelf(snapshot.shelves, code);
    if (!found) {
      setError('Полка с таким кодом не найдена');
      return;
    }
    if (selection && !locations.some(location => location.shelf.id === found.id)) {
      setError('На этой полке нет товара из выбранной позиции');
      return;
    }
    setError('');
    setShelf({ code, item: found });
    if (Platform.OS !== 'web') void Haptics.selectionAsync().catch(() => {});
  }

  async function save() {
    if (!product || !shelf || !validQuantity || formBusy.current) return;
    formBusy.current = true;
    setError('');
    setBusy(true);
    try {
      const state = await submit({
        kind: selection ? 'pick' : 'putaway',
        product_code: product.code,
        shelf_code: shelf.code,
        quantity: entered,
        ...(selection ? { order_line_id: selection.line.id } : {}),
      });
      setQueued(state === 'queued');
      setResult(`${product.item.name} · ${entered} шт. · ${shelf.item.code}`);
      if (Platform.OS !== 'web') void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить операцию');
    } finally {
      formBusy.current = false;
      setBusy(false);
    }
  }

  if (result) {
    return (
      <View style={[styles.card, opStyles.result]}>
        <View style={opStyles.resultIcon}>
          <Ionicons size={28} color={theme.green} name={queued ? 'time-outline' : 'checkmark'} />
        </View>
        <Text style={styles.heading}>{queued ? 'Операция в очереди' : selection ? 'Товар списан с полки' : 'Товар размещён'}</Text>
        <Text style={styles.caption}>{result}</Text>
        {queued && <Notice text="Операция сохранена на устройстве и будет отправлена, когда сервер станет доступен." tone="warning" />}
        {selection ? (
          <>
            {orderedQty !== null && orderedQty > 0 && locations.length > 0 && <Button label="Собрать ещё" icon="scan-outline" onPress={startAgain} />}
            {onDone && <Button label="Вернуться к заказу" icon="arrow-back-outline" variant="secondary" onPress={onDone} />}
          </>
        ) : <Button label="Разместить следующий товар" icon="scan-outline" onPress={startAgain} />}
      </View>
    );
  }

  if (selection && orderedQty === 0) {
    return (
      <View style={styles.stack}>
        <Empty title="Позиция собрана" icon="checkmark-circle-outline" message={expected?.name} />
        {onDone && <Button label="Вернуться к заказу" variant="secondary" onPress={onDone} />}
      </View>
    );
  }

  const phase = !product ? 1 : !shelf ? 2 : 3;
  return (
    <View style={styles.stack}>
      {selection && (
        <View style={styles.card}>
          <Text style={styles.heading}>{expected?.name ?? 'Товар'}</Text>
          <Text style={styles.caption}>Осталось собрать {orderedQty} шт.</Text>
          {locations.length
            ? <View style={opStyles.badges}>
                {locations.map(location => <Badge key={location.shelf.id} icon="location-outline">{location.shelf.code} · {location.quantity} шт.</Badge>)}
              </View>
            : <Notice tone="warning" text="Товар отсутствует на полках." />}
        </View>
      )}
      <View style={styles.card}>
        <StepHeading number={1} icon="barcode-outline" text="Штрихкод товара" done={!!product} />
        {product
          ? <Scanned title={product.item.name} detail={product.code} disabled={busy} onEdit={startAgain} />
          : <ScanField key={`product-${attempt}`} type="product" error={error} onScan={onProduct} onEdit={() => setError('')} />}
      </View>
      <View style={[styles.card, phase < 2 && opStyles.inactive]}>
        <StepHeading number={2} icon="qr-code-outline" text="Полка" done={!!shelf} />
        {shelf ? (
          <Scanned title={shelf.item.code} detail={shelf.item.zone} disabled={busy} onEdit={() => {
            setShelf(null);
            setError('');
            setQuantity('1');
          }} />
        ) : product ? (
          <ScanField key={`shelf-${attempt}`} type="shelf" error={error} onScan={onShelf} onEdit={() => setError('')} />
        ) : <Text style={styles.caption}>Сначала отсканируйте товар.</Text>}
      </View>
      {phase === 3 && (
        <View style={styles.card}>
          <StepHeading number={3} icon="layers-outline" text="Количество и подтверждение" done={false} />
          {selection && <Text style={styles.caption}>На выбранной полке {available} шт. Можно собрать до {limit} шт.</Text>}
          <Field label="Количество, шт." value={quantity} onChangeText={text => {
            setQuantity(text);
            if (error) setError('');
          }} keyboardType="number-pad" maxLength={6} editable={!busy} />
          {quantity && !validQuantity && <Notice text={limit > 0 ? `Введите число от 1 до ${limit}.` : 'Выберите полку с остатком этого товара.'} tone="warning" />}
          {error && <Notice text={error} tone="danger" />}
          <Button label={selection ? 'Подтвердить сборку' : 'Подтвердить размещение'} icon="checkmark-outline" busy={busy} disabled={!validQuantity} onPress={() => void save()} />
        </View>
      )}
    </View>
  );
}

function StepHeading({ number, icon, text, done }: { number: number; icon: 'barcode-outline' | 'qr-code-outline' | 'layers-outline'; text: string; done: boolean }) {
  return (
    <View style={styles.row}>
      <View style={opStyles.step}>
        <Text style={opStyles.stepNumber}>{number}</Text>
      </View>
      <Text style={[styles.heading, styles.stretch]}>{text}</Text>
      <Ionicons name={done ? 'checkmark-circle' : icon} size={21} color={theme.green} />
    </View>
  );
}

function Scanned({ title, detail, onEdit, disabled }: { title: string; detail?: string; onEdit: () => void; disabled: boolean }) {
  return (
    <View style={opStyles.scanned}>
      <View style={styles.stretch}>
        <Text style={styles.body}>{title}</Text>
        {detail && <Text style={styles.caption}>{detail}</Text>}
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel={`Изменить: ${title}`} onPress={onEdit} disabled={disabled} style={opStyles.edit}>
        <Text style={opStyles.editText}>Изменить</Text>
      </Pressable>
    </View>
  );
}

const opStyles = StyleSheet.create({
  inactive: { opacity: 0.68 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  step: { width: 35, height: 35, borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.pale },
  stepNumber: { color: theme.green, fontSize: 15, fontWeight: '800' },
  scanned: { ...styles.between, backgroundColor: theme.pale, paddingVertical: 9, paddingHorizontal: 12, borderRadius: 12 },
  edit: { minHeight: 41, minWidth: 56, alignItems: 'flex-end', justifyContent: 'center' },
  editText: { fontSize: 13, fontWeight: '800', color: theme.green },
  result: { alignItems: 'stretch', paddingVertical: 23 },
  resultIcon: { alignItems: 'center', justifyContent: 'center', width: 52, height: 52, backgroundColor: theme.pale, borderRadius: 15 },
});
