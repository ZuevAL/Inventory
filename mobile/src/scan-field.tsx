import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions, type BarcodeType } from 'expo-camera';
import { useRef, useState } from 'react';
import { Linking, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Field, Notice, styles, theme } from './ui';

const productTypes: BarcodeType[] = ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'itf14', 'datamatrix'];
const shelfTypes: BarcodeType[] = ['qr'];

export function ScanField({ type, error, onScan, onEdit }: {
  type: 'product' | 'shelf'; error: string; onScan: (value: string) => void; onEdit: () => void;
}) {
  const [value, setValue] = useState('');
  const [camera, setCamera] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [permission, requestPermission] = useCameraPermissions();
  const submitting = useRef(false);

  const shelf = type === 'shelf';
  const label = shelf ? 'Код полки' : 'Штрихкод товара';

  function submit(code: string) {
    const trimmed = code.trim();
    if (!trimmed) return;
    onScan(trimmed);
  }

  async function openCamera() {
    setCameraError('');
    try {
      if (!permission || (!permission.granted && permission.canAskAgain)) {
        const result = await requestPermission();
        if (!result.granted && result.canAskAgain) {
          setCameraError('Камера недоступна. Введите код вручную или используйте внешний сканер.');
          return;
        }
      }
      submitting.current = false;
      setCamera(true);
    } catch {
      setCameraError('Не удалось открыть камеру. Введите код вручную или используйте внешний сканер.');
    }
  }

  return (
    <View style={styles.stack}>
      <Field
        label={label}
        value={value}
        onChangeText={text => {
          setValue(text);
          if (error) onEdit();
        }}
        onSubmitEditing={() => submit(value)}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="off"
        returnKeyType="go"
        maxLength={500}
        placeholder={shelf ? 'Например, A-01-01' : 'Сканируйте или введите код'}
      />
      <View style={styles.row}>
        <Button label="Проверить код" style={styles.stretch} icon="checkmark-outline" onPress={() => submit(value)} disabled={!value.trim()} />
        {Platform.OS !== 'web' && (
          <Button label="Камера" style={styles.stretch} icon="scan-outline" onPress={() => void openCamera()} variant="secondary" />
        )}
      </View>
      {error && <Notice text={error} tone="danger" />}
      {cameraError && !camera && <Notice text={cameraError} tone="warning" />}
      {camera && (
        <Modal visible onRequestClose={() => setCamera(false)} animationType="fade">
          <SafeAreaView style={cameraStyles.screen}>
            <View style={cameraStyles.header}>
              <Text style={cameraStyles.title}>{shelf ? 'QR-код полки' : label}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Закрыть камеру" onPress={() => setCamera(false)} style={cameraStyles.close}>
                <Ionicons name="close" size={26} color="white" />
              </Pressable>
            </View>
            {permission?.granted && !cameraError ? (
              <View style={cameraStyles.viewport}>
                <CameraView
                  style={StyleSheet.absoluteFill}
                  facing="back"
                  barcodeScannerSettings={{ barcodeTypes: shelf ? shelfTypes : productTypes }}
                  onMountError={() => setCameraError('Камера не запустилась. Введите код вручную.')}
                  onBarcodeScanned={({ data }) => {
                    if (submitting.current || !data.trim()) return;
                    submitting.current = true;
                    setCamera(false);
                    setValue(data);
                    submit(data);
                  }}
                />
                <View pointerEvents="none" style={cameraStyles.overlay}>
                  <View style={[cameraStyles.target, shelf && cameraStyles.qrTarget]} />
                  <Text style={cameraStyles.hint}>Поместите код в рамку</Text>
                </View>
              </View>
            ) : (
              <View style={cameraStyles.message}>
                <Notice text={cameraError || 'Разрешите доступ к камере в настройках устройства.'} tone="warning" />
                {!cameraError && (
                  <Button label="Настройки устройства" icon="settings-outline" onPress={() => {
                    setCamera(false);
                    void Linking.openSettings().catch(() => setCameraError('Не удалось открыть настройки устройства.'));
                  }} />
                )}
                <Button label="Ввести вручную" variant="secondary" onPress={() => setCamera(false)} />
              </View>
            )}
          </SafeAreaView>
        </Modal>
      )}
    </View>
  );
}

const cameraStyles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.dark },
  header: { ...styles.between, paddingVertical: 10, paddingHorizontal: 17 },
  title: { fontSize: 19, fontWeight: '800', color: 'white' },
  close: { height: 45, width: 45, alignItems: 'center', justifyContent: 'center' },
  viewport: { flex: 1 },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: '#081A1C25', gap: 17 },
  target: { width: '80%', maxWidth: 340, height: 145, borderColor: theme.accent, borderWidth: 3, borderRadius: 17 },
  qrTarget: { width: 225, height: 225 },
  hint: { color: 'white', backgroundColor: theme.dark, paddingHorizontal: 15, paddingVertical: 8, borderRadius: 16, fontWeight: '700' },
  message: { padding: 17, gap: 14 },
});
