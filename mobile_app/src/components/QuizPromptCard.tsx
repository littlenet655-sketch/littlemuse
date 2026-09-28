import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { colors, radius, spacing } from '../ui/tokens';

/**
 * Dismissible non-blocking quiz prompt rendered inline between reels.
 * Tapping "Take the quiz" opens the Quiz screen voluntarily; the X dismisses
 * the card for the session. Content is never blocked by this card.
 */
export function QuizPromptCard({
  height,
  onTakeQuiz,
  onDismiss,
}: {
  height: number;
  onTakeQuiz: () => void;
  onDismiss: () => void;
}) {
  return (
    <View style={[styles.cell, { height }]} testID="quiz-prompt-card">
      <View style={styles.card} accessible accessibilityLabel="Brain break quiz prompt">
        <Pressable
          onPress={onDismiss}
          accessibilityRole="button"
          accessibilityLabel="Dismiss quiz prompt"
          testID="quiz-prompt-dismiss"
          hitSlop={10}
          style={styles.dismiss}
        >
          <Feather name="x" size={20} color="#94A3B8" />
        </Pressable>
        <View style={styles.badge}>
          <Feather name="zap" size={12} color="#FFFFFF" />
          <Text style={styles.badgeText}>BRAIN BREAK</Text>
        </View>
        <Text style={styles.title}>Time for a quick brain break!</Text>
        <Text style={styles.sub}>
          A short quiz is ready for you. Your reels keep playing — no rush.
        </Text>
        <Pressable
          onPress={onTakeQuiz}
          accessibilityRole="button"
          accessibilityLabel="Take the quiz"
          testID="quiz-prompt-take-quiz"
          style={styles.primary}
        >
          <Text style={styles.primaryText}>Take the quiz</Text>
        </Pressable>
        <Pressable
          onPress={onDismiss}
          accessibilityRole="button"
          accessibilityLabel="Not now"
          testID="quiz-prompt-not-now"
          style={styles.secondary}
        >
          <Text style={styles.secondaryText}>Not now</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  cell: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0F172A',
  },
  card: {
    position: 'relative',
    width: '86%',
    backgroundColor: '#FFFFFF',
    borderRadius: 24,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xl,
    alignItems: 'center',
    gap: 12,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 24,
    elevation: 8,
  },
  dismiss: {
    position: 'absolute',
    top: 8,
    right: 10,
    padding: 8,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: colors.brand,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  badgeText: { color: '#FFFFFF', fontWeight: '800', fontSize: 10, letterSpacing: 0.7 },
  title: {
    color: colors.ink,
    fontWeight: '800',
    fontSize: 20,
    lineHeight: 27,
    textAlign: 'center',
  },
  sub: {
    color: '#475569',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  primary: {
    backgroundColor: colors.brand,
    borderRadius: radius.pill,
    paddingHorizontal: 26,
    paddingVertical: 13,
    marginTop: 4,
    minWidth: 190,
    alignItems: 'center',
  },
  primaryText: { color: '#FFFFFF', fontWeight: '800', fontSize: 15 },
  secondary: {
    borderRadius: radius.pill,
    paddingHorizontal: 20,
    paddingVertical: 10,
    alignItems: 'center',
  },
  secondaryText: { color: '#64748B', fontWeight: '700', fontSize: 14 },
});
