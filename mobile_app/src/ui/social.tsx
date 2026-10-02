import { Image, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { colors, radius, spacing, storyGradient, storySeen, type } from './tokens';

export function Avatar({ uri, name, size = 36 }: { uri?: string | null; name?: string | null; size?: number }) {
  if (uri) return <Image source={{ uri }} style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]} />;
  const initial = (name ?? 'L').trim().charAt(0).toUpperCase() || 'L';
  return (
    <View style={[styles.fallback, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.initial, { fontSize: Math.max(12, size * 0.38) }]}>{initial}</Text>
    </View>
  );
}

/**
 * Instagram-style story ring: gradient stroke for unviewed stories, grey for
 * viewed. Wrap an <Avatar> inside; the white gap is handled here.
 */
export function StoryRing({
  size = 68,
  seen = false,
  children,
}: {
  size?: number;
  seen?: boolean;
  children: React.ReactNode;
}) {
  const stroke = 3;
  const center = size / 2;
  const r = center - stroke / 2;
  const inner = size - stroke * 2 - 5;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Defs>
          <LinearGradient id="littlenetStoryGrad" x1="0" y1="1" x2="1" y2="0">
            {storyGradient.map((stopColor, i) => (
              <Stop
                key={stopColor}
                offset={String(i / (storyGradient.length - 1))}
                stopColor={stopColor}
              />
            ))}
          </LinearGradient>
        </Defs>
        <Circle
          cx={center}
          cy={center}
          r={r}
          stroke={seen ? storySeen : 'url(#littlenetStoryGrad)'}
          strokeWidth={stroke}
          fill="none"
        />
      </Svg>
      <View
        style={{
          width: inner,
          height: inner,
          borderRadius: inner / 2,
          backgroundColor: colors.surface,
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        {children}
      </View>
    </View>
  );
}

export function TimeAgo({ value }: { value?: string }) {
  if (!value) return null;
  const t = Date.parse(value);
  const label = Number.isNaN(t) ? '' : shortAgo(Date.now() - t);
  if (!label) return null;
  return <Text style={styles.time}>{label}</Text>;
}

export function shortAgo(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function CategoryBadge({ label }: { label?: string }) {
  if (!label) return null;
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  avatar: { backgroundColor: colors.line },
  fallback: { backgroundColor: '#E8F3FA', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.line },
  initial: { fontWeight: '800', color: colors.ink, fontSize: type.body },
  time: { color: colors.muted, fontSize: type.caption },
  badge: { backgroundColor: '#E6F7F7', borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeText: { color: colors.teal, fontSize: type.caption, fontWeight: '700' },
});
