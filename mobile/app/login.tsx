import Ionicons from '@expo/vector-icons/Ionicons';
import { useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Brand, Button, Field, Notice, styles, theme } from '../src/ui';
import { useWarehouseContext } from '../src/warehouse-context';

export default function Login() {
  const {
    login, confirmLogin, setupPassword, cancelAuth, authStep, config, configure, session, logout,
  } = useWarehouseContext();
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [url, setUrl] = useState(config.url);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Действие не выполнено. Попробуйте ещё раз.');
    } finally {
      setBusy(false);
    }
  }

  function resetStep() {
    cancelAuth();
    setPassword('');
    setNewPassword('');
    setRepeatPassword('');
    setError('');
  }

  const recoveryRequired = session?.user.recovery_required;
  const configuring = showSettings && !session && !authStep;
  const confirming = authStep?.status === 'confirm_login';
  const settingPassword = authStep?.status === 'password_setup';
  const title = recoveryRequired ? 'Настройте восстановление доступа'
    : configuring ? 'Сервер склада' : confirming ? 'Подтвердите вход'
    : settingPassword ? 'Создайте пароль' : 'Вход на склад';

  return (
    <SafeAreaView style={loginStyles.page} edges={['top', 'right', 'bottom', 'left']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.stretch}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={loginStyles.content}>
          <View style={loginStyles.panel}>
            <View style={loginStyles.brand}><Brand /></View>
            <View style={loginStyles.form}>
              <Text accessibilityRole="header" style={styles.title}>{title}</Text>
              {recoveryRequired ? (
                <>
                  <Notice text="Откройте настройки безопасности в веб-версии склада, настройте восстановление доступа и войдите снова." tone="warning" />
                  <Button label="Выйти" icon="log-out-outline" onPress={() => void perform(logout)} busy={busy} />
                </>
              ) : configuring ? (
                <>
                  <Field
                    label="Адрес сервера"
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                    placeholder="https://склад.example"
                    value={url}
                    onChangeText={setUrl}
                  />
                  <Button label="Сохранить" busy={busy} disabled={!url.trim()} onPress={() => void perform(async () => {
                    await configure({ url: url.trim() });
                    setShowSettings(false);
                  })} />
                  <Button label="Назад" variant="secondary" disabled={busy} onPress={() => {
                    setShowSettings(false);
                    setError('');
                  }} />
                </>
              ) : confirming ? (
                <>
                  <Notice text={authStep.message} tone="warning" />
                  <Button label="Подтвердить вход" icon="checkmark-outline" busy={busy} onPress={() => void perform(confirmLogin)} />
                  <Button label="Отменить" variant="secondary" disabled={busy} onPress={resetStep} />
                </>
              ) : settingPassword ? (
                <>
                  <Text style={styles.caption}>{authStep.message}</Text>
                  <Field label="Новый пароль" autoCapitalize="none" autoComplete="new-password" value={newPassword} onChangeText={setNewPassword} secureTextEntry />
                  <Field label="Повторите пароль" autoCapitalize="none" autoComplete="new-password" value={repeatPassword} onChangeText={setRepeatPassword} secureTextEntry />
                  <Text style={styles.caption}>Минимум 15 символов.</Text>
                  <Button label="Установить пароль" busy={busy} disabled={!newPassword || !repeatPassword} onPress={() => void perform(async () => {
                    if (newPassword !== repeatPassword) throw new Error('Пароли не совпадают');
                    if (Array.from(newPassword).length < 15) throw new Error('Введите пароль длиной минимум 15 символов');
                    await setupPassword(newPassword);
                    setNewPassword('');
                    setRepeatPassword('');
                  })} />
                  <Button label="Отменить" variant="secondary" disabled={busy} onPress={resetStep} />
                </>
              ) : (
                <>
                  <Text style={styles.caption}>Войдите с учётной записью склада.</Text>
                  <Field label="Логин" autoCapitalize="none" autoComplete="username" value={name} onChangeText={setName} />
                  <Field label="Пароль" autoCapitalize="none" autoComplete="current-password" value={password} onChangeText={setPassword} secureTextEntry />
                  <Button label="Войти" icon="arrow-forward-outline" busy={busy} disabled={!name.trim() || !password} onPress={() => void perform(async () => {
                    await login(name.trim(), password);
                    setPassword('');
                  })} />
                  <Pressable accessibilityRole="button" accessibilityLabel="Настроить сервер" onPress={() => {
                    setError('');
                    setUrl(config.url);
                    setShowSettings(true);
                  }} disabled={busy} style={loginStyles.server}>
                    <Ionicons name="settings-outline" size={18} color={theme.green} />
                    <Text style={loginStyles.serverText}>Настроить сервер</Text>
                  </Pressable>
                </>
              )}
              {error ? <Notice text={error} tone="danger" /> : null}
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const loginStyles = StyleSheet.create({
  page: { flex: 1, backgroundColor: theme.dark },
  content: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: theme.canvas, paddingHorizontal: 16, paddingVertical: 24 },
  panel: { width: '100%', maxWidth: 454, overflow: 'hidden', borderRadius: 21, backgroundColor: 'white', borderWidth: 1, borderColor: theme.line },
  brand: { padding: 20, backgroundColor: theme.dark },
  form: { padding: 21, gap: 16 },
  server: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, minHeight: 42 },
  serverText: { color: theme.green, fontWeight: '800', fontSize: 14 },
});
