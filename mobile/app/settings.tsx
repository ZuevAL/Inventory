import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { Badge, Button, IconTile, Notice, Page, SectionTitle, styles } from '../src/ui';
import { useWarehouseContext } from '../src/warehouse-context';

export default function Settings() {
  const router = useRouter();
  const { session, config, logout, pending } = useWarehouseContext();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState('');

  async function signOut() {
    setError('');
    setBusy(true);
    try {
      await logout();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось завершить сессию');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page active="home">
      <SectionTitle title="Настройки" back={() => router.canGoBack() ? router.back() : router.replace('/')} />
      {session && (
        <View style={styles.card}>
          <View style={styles.row}>
            <IconTile icon="person-outline" />
            <View style={styles.stretch}>
              <Text style={styles.body}>{session.user.full_name}</Text>
              <Text style={styles.caption}>{session.user.login}</Text>
            </View>
            <Badge>{session.user.role === 'admin' ? 'Администратор' : 'Кладовщик'}</Badge>
          </View>
        </View>
      )}
      <View style={styles.card}>
        <Text style={styles.heading}>Сервер склада</Text>
        <Text selectable style={styles.body}>{config.url}</Text>
        <Text style={styles.caption}>Адрес сервера можно изменить на экране входа.</Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.heading}>Сессия</Text>
        {confirm ? (
          <>
            {pending.length > 0 && <Notice text="Операции в очереди останутся на устройстве. Для отправки войдите снова с этой учётной записью и тем же адресом сервера." tone="warning" />}
            <View style={styles.row}>
              <Button label="Отмена" variant="secondary" style={styles.stretch} disabled={busy} onPress={() => setConfirm(false)} />
              <Button label="Выйти" icon="log-out-outline" variant="danger" style={styles.stretch} busy={busy} onPress={() => void signOut()} />
            </View>
          </>
        ) : <Button label="Выйти из приложения" icon="log-out-outline" variant="secondary" onPress={() => setConfirm(true)} />}
        {error && <Notice text={error} tone="danger" />}
      </View>
    </Page>
  );
}
