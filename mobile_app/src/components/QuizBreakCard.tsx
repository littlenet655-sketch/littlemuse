import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { answerQuiz, fetchQuiz, type QuizAnswerResponse, type QuizItem } from '../api/auth';
import { colors, radius, spacing } from '../ui/tokens';

export const QUIZ_EVERY_N = 5;

export interface QuizMarker {
  __quizBreak: true;
  markerId: string;
}

export function isQuizMarker(value: unknown): value is QuizMarker {
  return Boolean(
    value &&
      typeof value === 'object' &&
      '__quizBreak' in value &&
      (value as { __quizBreak?: unknown }).__quizBreak === true,
  );
}

export function withQuizBreaks<T>(items: readonly T[], every = QUIZ_EVERY_N): Array<T | QuizMarker> {
  if (!Number.isFinite(every) || every <= 0) return [...items];
  const out: Array<T | QuizMarker> = [];
  items.forEach((item, index) => {
    out.push(item);
    const ordinal = index + 1;
    if (ordinal % every === 0 && ordinal < items.length + 1) {
      out.push({ __quizBreak: true, markerId: `quiz-${ordinal}` });
    }
  });
  return out;
}

export function QuizBreakCard({
  token,
  fullscreen = false,
}: {
  token?: string;
  fullscreen?: boolean;
}) {
  const [quiz, setQuiz] = useState<QuizItem | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [result, setResult] = useState<QuizAnswerResponse | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setLoading(false);
      setQuiz(null);
      return;
    }
    setLoading(true);
    void fetchQuiz(token, 1)
      .then((res) => {
        if (!cancelled) setQuiz(res.quizzes?.[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setQuiz(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const options = useMemo(() => quiz?.options ?? [], [quiz?.options]);

  async function submit(option: string) {
    if (!token || !quiz || busy || result) return;
    setAnswer(option);
    setBusy(true);
    try {
      const next = await answerQuiz(token, quiz.quiz_id, option);
      if (mounted.current) setResult(next);
    } catch {
      if (mounted.current) setAnswer(null);
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  if (loading) {
    return (
      <View style={[styles.card, fullscreen && styles.fullscreenCard]}>
        <ActivityIndicator color={fullscreen ? '#FFFFFF' : colors.brand} />
        <Text style={[styles.loadingText, fullscreen && styles.textOnDark]}>Loading brain break…</Text>
      </View>
    );
  }

  if (!quiz) return null;

  return (
    <View style={[styles.card, fullscreen && styles.fullscreenCard]}>
      <View style={styles.badgeRow}>
        <View style={styles.badge}>
          <Feather name="zap" size={12} color="#FFFFFF" />
          <Text style={styles.badgeText}>BRAIN BREAK</Text>
        </View>
        <Text style={[styles.category, fullscreen && styles.textOnDark]}>{quiz.category}</Text>
      </View>

      <Text style={[styles.question, fullscreen && styles.textOnDark]}>{quiz.question}</Text>

      <View style={styles.options}>
        {options.map((option) => {
          const chosen = answer === option;
          const correct = result?.correct && chosen;
          const wrong = result && !result.correct && chosen;
          return (
            <Pressable
              key={option}
              accessibilityRole="button"
              disabled={busy || Boolean(result)}
              onPress={() => void submit(option)}
              style={[
                styles.option,
                fullscreen && styles.optionDark,
                chosen && styles.optionChosen,
                correct && styles.optionCorrect,
                wrong && styles.optionWrong,
              ]}
            >
              <Text style={[styles.optionText, fullscreen && styles.textOnDark]}>{option}</Text>
            </Pressable>
          );
        })}
      </View>

      {busy ? <ActivityIndicator color={fullscreen ? '#FFFFFF' : colors.brand} /> : null}

      {result ? (
        <View style={[styles.feedback, result.correct ? styles.feedbackGood : styles.feedbackBad]}>
          <Text style={styles.feedbackTitle}>{result.correct ? `Nice! +${result.xp} XP` : 'Good try'}</Text>
          {!result.correct ? <Text style={styles.feedbackText}>Correct answer: {result.correct_answer}</Text> : null}
          {result.explanation ? <Text style={styles.feedbackText}>{result.explanation}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.md,
    marginVertical: spacing.md,
    padding: spacing.lg,
    borderRadius: 18,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#DBEAFE',
    gap: 14,
  },
  fullscreenCard: {
    flex: 1,
    marginHorizontal: 18,
    marginVertical: 28,
    justifyContent: 'center',
    backgroundColor: '#0F172A',
    borderColor: '#334155',
  },
  badgeRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
    backgroundColor: colors.brand,
    borderRadius: radius.pill,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  badgeText: { color: '#FFFFFF', fontWeight: '800', fontSize: 10, letterSpacing: 0.7 },
  category: { color: colors.muted, fontWeight: '700', fontSize: 12, flexShrink: 1, textAlign: 'right' },
  question: { color: colors.ink, fontWeight: '800', fontSize: 18, lineHeight: 25 },
  options: { gap: 9 },
  option: {
    minHeight: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#D7DEE8',
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  optionDark: { backgroundColor: '#111827', borderColor: '#475569' },
  optionChosen: { borderColor: colors.brand, borderWidth: 2 },
  optionCorrect: { backgroundColor: '#DCFCE7', borderColor: '#16A34A' },
  optionWrong: { backgroundColor: '#FEE2E2', borderColor: '#DC2626' },
  optionText: { color: colors.ink, fontWeight: '700', fontSize: 14, lineHeight: 20 },
  feedback: { borderRadius: 12, padding: 12, gap: 4 },
  feedbackGood: { backgroundColor: '#DCFCE7' },
  feedbackBad: { backgroundColor: '#FEF3C7' },
  feedbackTitle: { color: '#111827', fontWeight: '800', fontSize: 14 },
  feedbackText: { color: '#334155', fontSize: 13, lineHeight: 18 },
  loadingText: { color: colors.muted, textAlign: 'center', fontWeight: '700' },
  textOnDark: { color: '#F8FAFC' },
});
