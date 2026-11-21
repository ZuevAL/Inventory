import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { type ComponentProps, type ReactNode } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View, type TextInputProps, type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useWarehouseContext } from './warehouse-context';

export const theme = {
  canvas: '#F3F5F4',
  surface: '#FFFFFF',
  ink: '#142B2D',
  secondary: '#526464',
  line: '#DCE5E1',
  dark: '#102C2D',
  accent: '#BBF784',
  green: '#146541',
  pale: '#E4F2E9',
  warning: '#875000',
  warningBackground: '#FFF1D9',
  danger: '#A32C36',
  dangerBackground: '#FBE8E9',
};

export type IconName = ComponentProps<typeof Ionicons>['name'];
type Tab = 'home' | 'putaway' | 'orders' | 'stock';

export const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  stretch: { flex: 1, minWidth: 0 },
  stack: { gap: 12 },
  card: { padding: 18, gap: 12, borderRadius: 16, borderWidth: 1, borderColor: theme.line, backgroundColor: theme.surface },
  title: { color: theme.ink, fontSize: 29, lineHeight: 35, fontWeight: '800', letterSpacing: -0.8 },
  heading: { color: theme.ink, fontSize: 19, lineHeight: 25, fontWeight: '800', letterSpacing: -0.35 },
  body: { color: theme.ink, fontSize: 15, lineHeight: 21, fontWeight: '600' },
  caption: { color: theme.secondary, fontSize: 13, lineHeight: 19 },
  smallLabel: { color: theme.secondary, fontSize: 12, lineHeight: 17, fontWeight: '700', letterSpacing: 0.6 },
});

const tabs = [
  { key: 'home', href: '/', name: 'Обзор', icon: 'grid-outline' },
  { key: 'putaway', href: '/putaway', name: 'Раскладка', icon: 'cube-outline' },
  { key: 'orders', href: '/orders', name: 'Заказы', icon: 'clipboard-outline' },
  { key: 'stock', href: '/stock', name: 'Остатки', icon: 'layers-outline' },
] as const;

export function Brand() {
  return (
    <View style={styles.row} accessibilityLabel="Инвентаризация">
      <View style={ui.brandMark}><Ionicons name="cube-outline" size={21} color={theme.dark} /></View>
      <Text style={ui.brandName}>Инвентаризация</Text>
    </View>
  );
}

export function Page({ active, children }: { active: Tab; children: ReactNode }) {
  const router = useRouter();
  const { online, pending } = useWarehouseContext();
  const hasConflict = pending.some(operation => operation.status === 'conflict');
  const statusLabel = hasConflict
    ? 'Конфликты'
    : pending.length > 0 ? `В очереди: ${pending.length}` : online ? 'В сети' : 'Офлайн';

  return (
    <SafeAreaView style={ui.page} edges={['top', 'bottom', 'left', 'right']}>
      <View style={ui.header}>
        <View style={ui.headerInner}>
          <Brand />
          <View style={styles.row}>
            <Pressable
              accessibilityLabel={`Журнал операций, ${statusLabel}`}
              accessibilityRole="button"
              onPress={() => router.push('/activity')}
              style={ui.connection}
            >
              <View style={[ui.statusDot, { backgroundColor: hasConflict ? '#FFB3AD' : online ? theme.accent : '#FFD78D' }]} />
              <Text numberOfLines={1} style={ui.statusText}>{statusLabel}</Text>
            </Pressable>
            <Pressable accessibilityLabel="Настройки" accessibilityRole="button" onPress={() => router.push('/settings')} style={ui.settings}>
              <Ionicons name="settings-outline" size={20} color="white" />
            </Pressable>
          </View>
        </View>
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.stretch}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={ui.scroll}
        >
          <View style={ui.content}>{children}</View>
        </ScrollView>
      </KeyboardAvoidingView>
      <View style={ui.navigation}>
        <View style={ui.navigationInner}>
          {tabs.map(tab => {
            const selected = tab.key === active;
            return (
              <Pressable
                key={tab.key}
                accessibilityRole="tab"
                accessibilityLabel={tab.name}
                accessibilityState={{ selected }}
                onPress={() => router.replace(tab.href)}
                style={({ pressed }) => [ui.navItem, pressed && ui.pressed]}
              >
                <View style={[ui.navIcon, selected && ui.navIconActive]}>
                  <Ionicons size={21} color={selected ? theme.dark : theme.secondary} name={tab.icon} />
                </View>
                <Text style={[ui.navText, selected && ui.navTextActive]}>{tab.name}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </SafeAreaView>
  );
}

export function SectionTitle({ title, description, back, aside }: {
  title: string; description?: string; back?: () => void; aside?: ReactNode;
}) {
  return (
    <View style={ui.section}>
      {back && (
        <Pressable onPress={back} style={ui.back} accessibilityRole="button" accessibilityLabel="Назад">
          <Ionicons name="arrow-back" size={18} color={theme.green} />
          <Text style={ui.backText}>Назад</Text>
        </Pressable>
      )}
      <View style={styles.between}>
        <View style={styles.stretch}>
          <Text accessibilityRole="header" style={styles.title}>{title}</Text>
          {description && <Text style={[styles.caption, ui.description]}>{description}</Text>}
        </View>
        {aside}
      </View>
    </View>
  );
}

export function Button({ icon, label, onPress, disabled = false, busy = false, variant = 'primary', style }: {
  icon?: IconName; label: string; onPress: () => void; disabled?: boolean; busy?: boolean;
  variant?: 'primary' | 'secondary' | 'danger'; style?: ViewStyle;
}) {
  const color = variant === 'primary' ? theme.ink : variant === 'danger' ? theme.danger : theme.green;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        ui.button, variant === 'primary' ? ui.primary : ui.secondary,
        (disabled || busy) && ui.disabled, pressed && ui.pressed, style,
      ]}
    >
      {busy ? <ActivityIndicator size="small" color={color} /> : icon && <Ionicons name={icon} color={color} size={19} />}
      <Text style={[ui.buttonText, { color }]}>{label}</Text>
    </Pressable>
  );
}

export function Badge({ children, tone = 'neutral', icon }: {
  children: ReactNode; tone?: 'neutral' | 'good' | 'warning' | 'danger'; icon?: IconName;
}) {
  const [backgroundColor, color] = {
    neutral: [theme.canvas, theme.secondary], good: [theme.pale, theme.green],
    warning: [theme.warningBackground, theme.warning], danger: [theme.dangerBackground, theme.danger],
  }[tone];
  return (
    <View style={[ui.badge, { backgroundColor }]}>
      {icon && <Ionicons name={icon} size={15} color={color} />}
      <Text style={[ui.badgeText, { color }]}>{children}</Text>
    </View>
  );
}

export function Notice({ text, tone = 'neutral' }: {
  text: string; tone?: 'neutral' | 'good' | 'warning' | 'danger';
}) {
  const tones = {
    neutral: [theme.canvas, theme.secondary, 'information-circle-outline'],
    good: [theme.pale, theme.green, 'checkmark-circle-outline'],
    warning: [theme.warningBackground, theme.warning, 'alert-circle-outline'],
    danger: [theme.dangerBackground, theme.danger, 'alert-circle-outline'],
  } as const;
  const [backgroundColor, color, icon] = tones[tone];
  return (
    <View style={[ui.notice, { backgroundColor }]} accessibilityLiveRegion="polite">
      <Ionicons name={icon} size={21} color={color} />
      <Text style={[styles.caption, styles.stretch, { color }]}>{text}</Text>
    </View>
  );
}


export function Field({ label, ...input }: TextInputProps & { label: string }) {
  return (
    <View style={ui.fieldGroup}>
      <Text style={styles.body}>{label}</Text>
      <TextInput {...input} accessibilityLabel={input.accessibilityLabel ?? label} placeholderTextColor="#738181" style={[ui.input, input.style]} />
    </View>
  );
}

export function Empty({ title, message, icon = 'file-tray-outline' }: { title: string; message?: string; icon?: IconName }) {
  return (
    <View style={[styles.card, ui.empty]}>
      <IconTile icon={icon} color="green" />
      <Text style={styles.heading}>{title}</Text>
      {message && <Text style={[styles.caption, ui.centerText]}>{message}</Text>}
    </View>
  );
}

export function Busy({ label = 'Загрузка данных…' }: { label?: string }) {
  return (
    <View style={ui.busy} accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" color={theme.green} />
      <Text style={styles.caption}>{label}</Text>
    </View>
  );
}

export function IconTile({ icon, color = 'green' }: { icon: IconName; color?: 'green' | 'blue' | 'dark' }) {
  const [backgroundColor, foreground] = {
    green: [theme.pale, theme.green], blue: ['#EAEEF9', '#405888'], dark: [theme.dark, theme.accent],
  }[color];
  return (
    <View style={[ui.iconTile, { backgroundColor }]}><Ionicons name={icon} size={23} color={foreground} /></View>
  );
}

export function ListLink({ icon, title, detail, right, last, onPress }: {
  icon: IconName; title: string; detail?: string; right?: ReactNode; last?: boolean; onPress?: () => void;
}) {
  const content = (
    <>
      <IconTile icon={icon} color={icon === 'clipboard-outline' ? 'blue' : 'green'} />
      <View style={styles.stretch}>
        <Text style={styles.body}>{title}</Text>
        {detail && <Text style={styles.caption}>{detail}</Text>}
      </View>
      {right}
      {onPress && <Ionicons name="chevron-forward" size={19} color={theme.secondary} />}
    </>
  );
  const row = [ui.listLink, last && ui.last];
  return onPress
    ? <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [...row, pressed && ui.pressed]}>{content}</Pressable>
    : <View style={row}>{content}</View>;
}

const ui = StyleSheet.create({
  page: { flex: 1, backgroundColor: theme.dark },
  header: { backgroundColor: theme.dark },
  headerInner: { width: '100%', maxWidth: 1064, alignSelf: 'center', minHeight: 64, paddingHorizontal: 16, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  brandMark: { height: 35, width: 35, backgroundColor: theme.accent, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  brandName: { fontSize: 14, color: 'white', fontWeight: '800', letterSpacing: -0.2 },
  connection: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 9, minHeight: 38, borderRadius: 100, backgroundColor: '#223E40' },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  statusText: { color: 'white', fontSize: 11, fontWeight: '700' },
  settings: { width: 38, height: 40, alignItems: 'center', justifyContent: 'center' },
  scroll: { flexGrow: 1, gap: 19, paddingHorizontal: 16, paddingTop: 23, paddingBottom: 32, backgroundColor: theme.canvas },
  content: { width: '100%', maxWidth: 1032, alignSelf: 'center', gap: 19 },
  section: { alignSelf: 'center', width: '100%', maxWidth: 1032, gap: 8 },
  description: { marginTop: 5 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 32, alignSelf: 'flex-start' },
  backText: { color: theme.green, fontSize: 14, fontWeight: '700' },
  navigation: { backgroundColor: theme.surface, borderTopWidth: 1, borderTopColor: theme.line },
  navigationInner: { width: '100%', maxWidth: 660, alignSelf: 'center', flexDirection: 'row', paddingHorizontal: 8, paddingVertical: 6 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, minHeight: 54 },
  navIcon: { borderRadius: 15, paddingHorizontal: 15, paddingVertical: 5 },
  navIconActive: { backgroundColor: theme.accent },
  navText: { color: theme.secondary, fontSize: 11, lineHeight: 14, fontWeight: '600', textAlign: 'center' },
  navTextActive: { color: theme.ink, fontWeight: '800' },
  pressed: { opacity: 0.74 },
  button: { minHeight: 48, paddingHorizontal: 13, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 12, gap: 8 },
  primary: { backgroundColor: theme.accent },
  secondary: { backgroundColor: 'white', borderWidth: 1, borderColor: theme.line },
  disabled: { opacity: 0.54 },
  buttonText: { fontSize: 14, lineHeight: 19, fontWeight: '800', textAlign: 'center', flexShrink: 1 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 100, paddingHorizontal: 9, paddingVertical: 5, flexShrink: 1 },
  badgeText: { fontSize: 11, lineHeight: 15, fontWeight: '800' },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 12, padding: 12 },
  input: { backgroundColor: 'white', borderRadius: 12, color: theme.ink, paddingHorizontal: 12, paddingVertical: 11, minHeight: 47, borderWidth: 1, borderColor: '#C9D6D0', fontSize: 16 },
  fieldGroup: { gap: 6 },
  empty: { alignItems: 'center', paddingVertical: 29 },
  centerText: { textAlign: 'center' },
  busy: { alignItems: 'center', justifyContent: 'center', gap: 12, paddingVertical: 30 },
  iconTile: { height: 43, width: 43, alignItems: 'center', justifyContent: 'center', borderRadius: 12 },
  listLink: { flexDirection: 'row', alignItems: 'center', gap: 11, minHeight: 71, padding: 12, borderBottomWidth: 1, borderColor: theme.line },
  last: { borderBottomWidth: 0 },
});
