import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { answerQuiz, fetchQuiz, type QuizItem } from '../api/auth';
import { colors, radius, spacing } from '../ui/tokens';

type Phase = 'loading' | 'ready' | 'answered' | 'empty';

/**
 * Inline quiz break injected every QUIZ_EVERY_N content items in feed/reels.
 * Fetches one quiz lazily on mount (only when the cell scrolls into view),
 * lets the kid answer inline, and shows correct/wrong feedback with XP.
 * Renders nothing when the quiz bank is unavailable — the break is a bonus,
 * never a blocker.
 */
export function QuizBreakCard({ token, fullscreen = false }: { token: string; fullscreen?: boolean }) {
  const [phase, setPhase] = useState<Phase>('loading');
  const [quiz, setQuiz] = useState<QuizItem | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [correct, setCorrect] = useState<boolean | null>(null);
  const [correctAnswer, setCorrectAnswer] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [xp, setXp] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchQuiz(token, 1)
      .then((res) => {
        if (cancelled) return;
        const first = res.quizzes?.[0] ?? null;
        if (first) {
          setQuiz(first);
          setPhase('ready');
        } else {
          setPhase('empty');
        }
      })
      .catch(() => {
        if (!cancelled) setPhase('empty');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const answer = useCallback(
    async (option: string) => {
      if (!quiz || busy || phase !== 'ready') return;
      setBusy(true);
      setPicked(option);
      try {
        const res = await answerQuiz(token, quiz.quiz_id, option);
        setCorrect(res.correct);
        setCorrectAnswer(res.correct_answer || null);
        setExplanation(res.explanation || null);
        setXp(res.xp || 0);
      } catch {
        // Fail soft: a network blip must not trap the kid on the card.
        setCorrect(null);
      } finally {
        setBusy(false);
        setPhase('answered');
      }
    },
    [quiz, busy, phase, token],
  );

  if (phase === 'empty' || phase === 'loading') {
    // Loading shows a slim placeholder so layout doesn't jump; empty renders
    // nothing at all (the FlatList keeps a zero-height row).
    if (phase === 'empty') return null;
    return (
      <View style={[styles.card, fullscreen && styles.cardFullscreen]}>
        <ActivityIndicator size="small" color={colors.brand} />
        <Text style={styles.loadingText}>Getting a quick quiz…</Text>
      </View>
    );
  }

  if (!quiz) return null;

  return (
    <View style={[styles.card, fullscreen && styles.cardFullscreen]}>
      <View style={styles.badgeRow}>
        <View style={styles.badge}>
          <Feather name="help-circle" size={13} color="#FFFFFF" />
          <Text style={styles.badgeText}>Quick quiz</Text>
        </View>
        <Text style={styles.category}>{quiz.category}</Text>
      </View>
      <Text style={styles.question}>{quiz.question}</Text>
      <View style={styles.options}>
        {quiz.options.map((option) => {
          const isPicked = picked === option;
          const isRight = phase === 'answered' && correctAnswer === option;
          return (
            <Pressable
              key={option}
              onPress={() => void answer(option)}
              disabled={phase !== 'ready' || busy}
              accessibilityRole="button"
              accessibilityLabel={`Answer: ${option}`}
              style={[
                styles.option,
                isPicked && styles.optionPicked,
                isRight && styles.optionCorrect,
                phase === 'answered' && isPicked && correct === false && styles.optionWrong,
              ]}
            >
              <Text style={[styles.optionText, (isPicked || isRight) && styles.optionTextActive]}>
                {option}
              </Text>
              {phase === 'answered' && isRight ? (
                <Feather name="check-circle" size={18} color="#16A34A" />
              ) : null}
              {phase === 'answered' && isPicked && correct === false ? (
                <Feather name="x-circle" size={18} color="#DC2626" />
              ) : null}
            </Pressable>
          );
        })}
      </View>
      {phase === 'answered' ? (
        <View style={styles.feedback}>
          {correct === true ? (
            <Text style={styles.feedbackGood}>Nice!{xp > 0 ? ` +${xp} XP` : ''}</Text>
          ) : correct === false ? (
            <Text style={styles.feedbackBad}>Good try — keep learning!</Text>
          ) : (
            <Text style={styles.feedbackMuted}>Answer saved.</Text>
          )}
          {explanation ? <Text style={styles.explanation}>{explanation}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

/** Insert a quiz marker after every N content items. */
export const QUIZ_EVERY_N = 5;

export type QuizMarker = { __quizBreak: true; markerId: string };

export function withQuizBreaks<T>(items: T[]): Array<T | QuizMarker> {
  const out: Array<T | QuizMarker> = [];
  items.forEach((item, idx) => {
    out.push(item);
    if ((idx + 1) % QUIZ_EVERY_N === 0) {
      out.push({ __quizBreak: true, markerId: `quiz-${idx}` });
    }
  });
  return out;
}

export function isQuizMarker(item: unknown): item is QuizMarker {
  return (
    typeof item === 'object' &&
    item !== null &&
    (item as Record<string, unknown>).__quizBreak === true
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginHorizontal: spacing.md,
    marginVertical: spacing.sm,
    borderWidth: 1,
    borderColor: '#F3D9E4',
    gap: 10,
  },
  cardFullscreen: {
    marginHorizontal: spacing.lg,
    alignSelf: 'center',
    width: '88%',
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.brand,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 14,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '800',
  },
  category: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.muted,
    textTransform: 'uppercase',
  },
  question: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
    lineHeight: 22,
  },
  loadingText: {
    fontSize: 13,
    color: colors.muted,
    textAlign: 'center',
  },
  options: { gap: 8 },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FFF7FA',
    borderWidth: 1,
    borderColor: '#F3D9E4',
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
  },
  optionPicked: {
    borderColor: colors.brand,
    backgroundColor: '#FDF0F5',
  },
  optionCorrect: {
    borderColor: '#16A34A',
    backgroundColor: '#F0FDF4',
  },
  optionWrong: {
    borderColor: '#DC2626',
    backgroundColor: '#FEF2F2',
  },
  optionText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.ink,
    flex: 1,
  },
  optionTextActive: { fontWeight: '800' },
  feedback: { gap: 4 },
  feedbackGood: {
    fontSize: 14,
    fontWeight: '800',
    color: '#16A34A',
  },
  feedbackBad: {
    fontSize: 14,
    fontWeight: '800',
    color: '#B45309',
  },
  feedbackMuted: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.muted,
  },
  explanation: {
    fontSize: 13,
    color: colors.muted,
    lineHeight: 18,
  },
});
