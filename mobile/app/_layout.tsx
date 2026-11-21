import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { Busy, theme } from '../src/ui';
import { WarehouseProvider, useWarehouseContext } from '../src/warehouse-context';

export default function RootLayout() {
  return <WarehouseProvider><Routes /></WarehouseProvider>;
}

function Routes() {
  const { authReady, session } = useWarehouseContext();

  if (!authReady) {
    return <View style={{ flex: 1, backgroundColor: theme.canvas, justifyContent: 'center' }}><Busy label="Восстановление сессии…" /></View>;
  }
  const authorized = !!session && !session.user.recovery_required;
  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, animation: 'fade', contentStyle: { backgroundColor: theme.canvas } }}>
        <Stack.Protected guard={authorized}>
          <Stack.Screen name="index" />
          <Stack.Screen name="putaway" />
          <Stack.Screen name="orders/index" />
          <Stack.Screen name="orders/[id]" />
          <Stack.Screen name="pick/[id]" />
          <Stack.Screen name="stock" />
          <Stack.Screen name="activity" />
          <Stack.Screen name="settings" />
        </Stack.Protected>
        <Stack.Protected guard={!authorized}>
          <Stack.Screen name="login" />
        </Stack.Protected>
      </Stack>
    </>
  );
}
