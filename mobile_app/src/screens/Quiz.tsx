import { useCallback, useEffect, useRef, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { answerQuiz, fetchQuiz } from '../api/auth';
import type { QuizItem } from '../api/auth';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import { clearPendingDestination, loadPendingDestination, savePendingDestination } from '../auth/session';
import { secureStoreBackend } from '../auth/storage';
import type { ChildScreenProps, ChildStackParamList } from '../navigation/types';
import { quizLoadStatus, shouldProceedAfterRefresh } from '../quiz/decision';
import { Button, Card, GateNotice, LoadingState, Notice, Screen } from '../ui/components';
import { colors, radius, spacing, type } from '../ui/tokens';

interface QuizScreenParams {
  /** Where to return after a required quiz completes. */
  returnTo?: string;
  autoStart?: boolean;
}

type Phase = 'loading' | 'hub' | 'ready' | 'unavailable' | 'complete';

const OPTION_LABELS = ['A', 'B', 'C', 'D', 'E', 'F'];

/**
 * Route names the quiz-completion reset is allowed to target. The stored
 * destination comes from unvalidated SecureStore (via route params), so a
 * stale or garbage string must fall back to 'KidsTabs' instead of resetting
 * to a nonexistent route. Typed against the real param list so a typo here
 * fails typecheck.
 *
 * SECURITY: only routes that take NO required params may be listed here.
 * `navigation.reset` supplies no params, so a param-required route
 * (Chat/ChatDetails need peerId, PostDetail/ProcessingStatus need postId,
 * OtherProfile needs targetId) would crash or soft-lock on load when reached
 * via a tampered pending-destination value.
 */
const KNOWN_QUIZ_DESTINATIONS: ReadonlySet<keyof ChildStackParamList> = new Set([
  'Quiz', 'KidsTabs', 'FeedTab', 'DiscoverTab', 'CreateTab', 'ReelsTab',
  'ProfileTab', 'Stories', 'NotificationsTab', 'Conversations',
  'NewMessage', 'SavedContent', 'EditProfile', 'Connections',
  'SafetyCentre', 'ReportHistory',
]);

/** Resolve a stored pending destination to a real route, else 'KidsTabs'. */
function resolveQuizDestination(stored: string | null): keyof ChildStackParamList {
  return stored && KNOWN_QUIZ_DESTINATIONS.has(stored as keyof ChildStackParamList)
    ? (stored as keyof ChildStackParamList)
    : 'KidsTabs';
}

/**
 * Mandatory onboarding quiz + recurring feed quiz gate with gamified child UI.
 * Forward navigation happens only after an authoritative /me refresh
 * confirms the gates are clear. Refresh failure keeps the child gated
 * with retry; an empty required bank shows unavailable, never "All done".
 */
export function QuizScreen({ navigation, route }: ChildScreenProps<'Quiz'>) {
  const { session, refreshMe } = useAuth();
  const params = (route.params ?? {}) as QuizScreenParams;
  const [items, setItems] = useState<QuizItem[]>([]);
  const [reason, setReason] = useState('');
  const [required, setRequired] = useState(true);
  const [index, setIndex] = useState(0);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [lastCorrect, setLastCorrect] = useState<boolean | null>(null);
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<unknown>(null);
  const [gateMessage, setGateMessage] = useState('');
  const [correctCount, setCorrectCount] = useState(0);
  const [earnedXp, setEarnedXp] = useState(0);
  /**
   * Per-question submission guard. Stays engaged after answerQuiz resolves
   * until the 1.1s feedback timeout fires, so a second tap during the
   * feedback window cannot double-submit the same question (double XP,
   * double correctCount, double index advance). The ref is the synchronous
   * guard; the state drives the disabled UI on the option Pressables.
   */
  const submittedKeyRef = useRef<string | null>(null);
  const [submittedKey, setSubmittedKey] = useState<string | null>(null);
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  function clearPendingTimeouts() {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
  }

  function scheduleTimeout(cb: () => void, ms: number) {
    const id = setTimeout(cb, ms);
    timeoutsRef.current.push(id);
  }

  const load = useCallback(async () => {
    if (!session) return;
    // A reload mid-feedback-window must not let a stale timeout skip a
    // question or double-fire completeQuiz from the previous attempt.
    clearPendingTimeouts();
    setPhase('loading');
    setError(null);
    setGateMessage('');
    try {
      const response = await fetchQuiz(session.token);
      if (quizLoadStatus(response.quizzes.length) === 'unavailable') {
        setPhase('unavailable');
        return;
      }
      setItems(response.quizzes);
      setReason(response.reason);
      setRequired(response.required);
      setIndex(0);
      setSelectedOption(null);
      setLastCorrect(null);
      setFeedback('');
      if (params.returnTo) await savePendingDestination(secureStoreBackend, params.returnTo);
      setCorrectCount(0);
      setEarnedXp(0);
      setPhase((response.required || params.autoStart) ? 'ready' : 'hub');
    } catch (err) {
      setError(err);
      setPhase('ready');
    }
  }, [session, params.returnTo]);

  useEffect(() => {
    void load();
  }, [load]);

  // Fix 2: navigating away mid-feedback-window must not fire setState/completeQuiz.
  useEffect(() => clearPendingTimeouts, []);

  /** Authoritative completion: refresh gates, proceed only when clear. */
  async function completeQuiz() {
    setBusy(true);
    setGateMessage('');
    try {
      const next = await refreshMe();
      if (!shouldProceedAfterRefresh(next.onboarding)) {
        setGateMessage('The safety check still shows a required step. Reloading your quiz…');
        await load();
        return;
      }
      const stored = await loadPendingDestination(secureStoreBackend);
      const destination = resolveQuizDestination(stored);
      await clearPendingDestination(secureStoreBackend);
      navigation.reset({ index: 0, routes: [{ name: destination }] });
    } catch (err) {
      // 401: the session is cleared upstream and the navigator leaves the
      // quiz; the finally below still resets busy so nothing is left disabled.
      if (err instanceof ApiError && err.status === 401) return;
      setGateMessage('Could not confirm quiz completion. Check your connection and retry — you are still safely gated.');
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswer(option: string) {
    if (!session || busy || phase !== 'ready') return;
    const current = items[index];
    if (!current) return;
    const key = `${index}:${current.quiz_id}`;
    if (submittedKeyRef.current === key) return;
    submittedKeyRef.current = key;
    setSubmittedKey(key);
    setBusy(true);
    setSelectedOption(option);
    setFeedback('');
    try {
      const result = await answerQuiz(session.token, current.quiz_id, option);
      setLastCorrect(result.correct);
      if (result.correct) setCorrectCount((value) => value + 1);
      setEarnedXp((value) => value + result.xp);
      setFeedback(result.correct ? `🌟 Correct! +${result.xp} XP. ${result.explanation ?? ''}`.trim() : `💡 ${result.explanation ?? 'Keep trying!'}`.trim());
      const lastItem = index + 1 >= items.length;
      if (result.onboarding_complete || !result.required || lastItem) {
        scheduleTimeout(() => {
          submittedKeyRef.current = null;
          setSubmittedKey(null);
          if (required) void completeQuiz();
          else setPhase('complete');
        }, 1100);
        return;
      }
      scheduleTimeout(() => {
        setIndex((value) => value + 1);
        setSelectedOption(null);
        setLastCorrect(null);
        setFeedback('');
        submittedKeyRef.current = null;
        setSubmittedKey(null);
      }, 1100);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setFeedback(err instanceof ApiError ? err.message : 'Could not check that answer. Try again.');
      setSelectedOption(null);
      setLastCorrect(null);
      // Allow retry after a failure: the guard only blocks resubmission of an accepted answer.
      submittedKeyRef.current = null;
      setSubmittedKey(null);
    } finally {
      setBusy(false);
    }
  }

  if (phase === 'loading') {
    return (
      <Screen>
        <LoadingState message="Loading your safety adventure…" />
      </Screen>
    );
  }

  if (phase === 'unavailable') {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.heroBanner}>
            <View style={styles.heroIconBadge}>
              <Feather name="shield" size={32} color="#0095F6" />
            </View>
            <Text style={styles.heroTitle}>Safety Quiz</Text>
            <Text style={styles.heroSubtitle}>Quizzes are temporarily updating.</Text>
          </View>
          <Card>
            <Notice tone="info" message="We could not load your safety quiz right now. You are still safely protected — pull or tap retry in a moment." />
            <Button label="Retry" onPress={() => void load()} />
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  if (error && items.length === 0) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.heroBanner}>
            <View style={styles.heroIconBadge}>
              <Feather name="alert-circle" size={32} color="#EF4444" />
            </View>
            <Text style={styles.heroTitle}>Safety Quiz</Text>
          </View>
          <Card>
            <GateNotice error={error} />
            <Button label="Retry" onPress={() => void load()} />
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  if (phase === 'hub') {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.heroBanner}>
            <View style={styles.heroIconBadge}>
              <Image source={require('../../assets/app_logo.png')} style={styles.heroLogoImg} />
            </View>
            <Text style={styles.heroTitle}>Learning Hub 🚀</Text>
            <Text style={styles.heroSubtitle}>Learn internet safety, earn XP, and level up your badges!</Text>
          </View>

          <Card style={styles.statsCard}>
            <View style={styles.statBox}>
              <Text style={styles.statVal}>{items.length}</Text>
              <Text style={styles.statLbl}>Questions</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statBox}>
              <Text style={[styles.statVal, { color: '#10B981' }]}>+{earnedXp}</Text>
              <Text style={styles.statLbl}>XP Earned</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statBox}>
              <Text style={[styles.statVal, { color: '#F59E0B' }]}>⭐</Text>
              <Text style={styles.statLbl}>Safe Explorer</Text>
            </View>
          </Card>

          <Card>
            <Text style={styles.sectionHeader}>Topics in this Quest</Text>
            <View style={styles.topicWrap}>
              {Array.from(new Set(items.map((item) => item.category))).map((category) => (
                <View key={category} style={styles.topicPill}>
                  <Feather name="check" size={13} color="#6366F1" style={{ marginRight: 4 }} />
                  <Text style={styles.topicPillText}>{category}</Text>
                </View>
              ))}
            </View>
            <View style={styles.hubActionBox}>
              <Button
                label="Start Safety Quest 🎮"
                onPress={() => {
                  setIndex(0);
                  setSelectedOption(null);
                  setLastCorrect(null);
                  setFeedback('');
                  setPhase('ready');
                }}
              />
              {!required ? (
                <>
                  <View style={{ height: 10 }} />
                  <Button
                    label="Back to Feed"
                    variant="secondary"
                    onPress={() => {
                      if (navigation.canGoBack()) navigation.goBack();
                      else navigation.navigate('KidsTabs');
                    }}
                  />
                </>
              ) : null}
            </View>
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  if (phase === 'complete') {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.celebrationHero}>
            <View style={styles.celebrationIconBadge}>
              <Feather name="award" size={48} color="#F59E0B" />
            </View>
            <Text style={styles.celebrationTitle}>Quest Complete! 🎉</Text>
            <Text style={styles.celebrationSubtitle}>You answered safety questions and leveled up!</Text>
            <View style={styles.xpBadge}>
              <Text style={styles.xpBadgeText}>+{earnedXp} XP EARNED</Text>
            </View>
          </View>

          <Card>
            <View style={styles.scoreRow}>
              <Feather name="check-circle" size={24} color="#10B981" />
              <Text style={styles.scoreText}>
                {correctCount} of {items.length} Correct
              </Text>
            </View>
            <Text style={styles.scoreSubtext}>
              Keep exploring! Practice quizzes sharpen your online safety knowledge.
            </Text>
            <View style={styles.completeActions}>
              <Button
                label="Practice Again"
                onPress={() => {
                  setIndex(0);
                  setSelectedOption(null);
                  setLastCorrect(null);
                  setCorrectCount(0);
                  setEarnedXp(0);
                  setFeedback('');
                  setPhase('ready');
                }}
              />
              <View style={{ height: 10 }} />
              <Button label="Back to Learning Hub" variant="secondary" onPress={() => setPhase('hub')} />
              {!required ? (
                <>
                  <View style={{ height: 10 }} />
                  <Button
                    label="Done & Return to Feed 🎉"
                    onPress={() => {
                      if (navigation.canGoBack()) navigation.goBack();
                      else navigation.navigate('KidsTabs');
                    }}
                  />
                </>
              ) : null}
            </View>
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  const current = items[index];
  if (!current) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.heroBanner}>
            <View style={styles.heroIconBadge}>
              <Feather name="check-circle" size={32} color="#10B981" />
            </View>
            <Text style={styles.heroTitle}>Safety Quiz</Text>
            <Text style={styles.heroSubtitle}>Checking your progress…</Text>
          </View>
          <Card>
            <Notice tone="info" message="Verifying your quiz completion with the LittleNet server…" />
            <Button
              label={busy ? 'Checking…' : 'Continue to LittleNet 🌟'}
              onPress={() => void completeQuiz()}
              loading={busy}
              disabled={busy}
            />
            {gateMessage ? <Notice tone="info" message={gateMessage} /> : null}
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header Hero */}
        <View style={styles.quizHeader}>
          <View style={styles.quizTopMeta}>
            <View style={styles.categoryBadge}>
              <Feather name="shield" size={13} color="#0095F6" style={{ marginRight: 5 }} />
              <Text style={styles.categoryBadgeText}>{current.category || 'Safety'}</Text>
            </View>
            <View style={styles.xpPill}>
              <Text style={styles.xpPillText}>+20 XP</Text>
            </View>
          </View>

          <Text style={styles.quizMainTitle}>
            {reason === 'onboarding' ? 'Welcome Safety Quiz' : reason === 'feed_break' ? 'Brain Break Challenge' : 'Safety Quest'}
          </Text>
          <Text style={styles.quizStepCounter}>
            Question {index + 1} of {items.length}
          </Text>

          {/* Dynamic Animated Progress Bar */}
          <View style={styles.progressContainer}>
            <View style={[styles.progressBarFill, { width: `${((index + 1) / items.length) * 100}%` }]} />
          </View>
        </View>

        {/* Question Card */}
        <Card style={styles.questionCard}>
          <Text style={styles.questionPrompt}>{current.question}</Text>

          {/* Interactive Option Cards */}
          <View style={styles.optionsList}>
            {current.options.map((option, optIdx) => {
              const isSelected = selectedOption === option;
              const isCorrectChoice = isSelected && lastCorrect === true;
              const isWrongChoice = isSelected && lastCorrect === false;

              return (
                <Pressable
                  key={option}
                  disabled={busy || submittedKey !== null}
                  onPress={() => void submitAnswer(option)}
                  style={({ pressed }) => [
                    styles.optionCard,
                    pressed && styles.optionCardPressed,
                    isSelected && styles.optionCardSelected,
                    isCorrectChoice && styles.optionCardCorrect,
                    isWrongChoice && styles.optionCardWrong,
                  ]}
                >
                  <View
                    style={[
                      styles.optionLetterBadge,
                      isSelected && styles.optionLetterBadgeSelected,
                      isCorrectChoice && styles.optionLetterBadgeCorrect,
                      isWrongChoice && styles.optionLetterBadgeWrong,
                    ]}
                  >
                    <Text
                      style={[
                        styles.optionLetterText,
                        isSelected && styles.optionLetterTextActive,
                      ]}
                    >
                      {OPTION_LABELS[optIdx] || String(optIdx + 1)}
                    </Text>
                  </View>
                  <Text
                    style={[
                      styles.optionLabel,
                      isSelected && styles.optionLabelSelected,
                      isCorrectChoice && styles.optionLabelCorrect,
                      isWrongChoice && styles.optionLabelWrong,
                    ]}
                  >
                    {option}
                  </Text>
                  {isCorrectChoice ? (
                    <Feather name="check" size={20} color="#10B981" style={styles.optionEndIcon} />
                  ) : isWrongChoice ? (
                    <Feather name="x" size={20} color="#EF4444" style={styles.optionEndIcon} />
                  ) : null}
                </Pressable>
              );
            })}
          </View>

          {feedback ? (
            <View
              style={[
                styles.feedbackContainer,
                feedback.includes('Correct') ? styles.feedbackOk : styles.feedbackInfo,
              ]}
            >
              <Text
                style={[
                  styles.feedbackText,
                  feedback.includes('Correct') ? styles.feedbackTextOk : styles.feedbackTextInfo,
                ]}
              >
                {feedback}
              </Text>
            </View>
          ) : null}

          {gateMessage ? <Notice tone="info" message={gateMessage} /> : null}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  scrollContent: { paddingBottom: spacing.xl },
  heroBanner: {
    alignItems: 'center',
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  heroIconBadge: {
    width: 64,
    height: 64,
    borderRadius: 20,
    backgroundColor: '#EBF5FF',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xs,
    elevation: 4,
    shadowColor: '#0095F6',
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
  },
  heroLogoImg: { width: 44, height: 44, borderRadius: 12 },
  heroTitle: {
    color: colors.ink,
    fontSize: 26,
    fontWeight: '900',
    letterSpacing: -0.5,
    marginTop: 6,
  },
  heroSubtitle: {
    color: colors.muted,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 4,
    lineHeight: 20,
    maxWidth: 320,
  },
  statsCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingVertical: 16,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  statBox: { alignItems: 'center' },
  statVal: { color: colors.brand, fontSize: 24, fontWeight: '900' },
  statLbl: { color: colors.muted, fontSize: 12, fontWeight: '600', marginTop: 2 },
  statDivider: { width: 1, height: 32, backgroundColor: colors.line },
  sectionHeader: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: 12,
  },
  topicWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  topicPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EEF2FF',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: radius.pill,
  },
  topicPillText: { color: '#4F46E5', fontWeight: '700', fontSize: 12 },
  hubActionBox: { marginTop: 8 },
  celebrationHero: {
    alignItems: 'center',
    paddingTop: spacing.xl,
    paddingBottom: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  celebrationIconBadge: {
    width: 80,
    height: 80,
    borderRadius: 26,
    backgroundColor: '#FEF3C7',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
    elevation: 6,
    shadowColor: '#F59E0B',
    shadowOpacity: 0.25,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
  },
  celebrationTitle: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: -0.5,
  },
  celebrationSubtitle: {
    color: colors.muted,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 6,
    lineHeight: 20,
  },
  xpBadge: {
    marginTop: 14,
    backgroundColor: '#ECFDF5',
    borderWidth: 1.5,
    borderColor: '#A7F3D0',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  xpBadgeText: {
    color: '#059669',
    fontWeight: '900',
    fontSize: 14,
    letterSpacing: 0.5,
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 8,
  },
  scoreText: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.ink,
  },
  scoreSubtext: {
    fontSize: 13,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 18,
    marginTop: 4,
    marginBottom: 16,
  },
  completeActions: { width: '100%' },
  quizHeader: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  quizTopMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E0F2FE',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  categoryBadgeText: {
    color: '#0284C7',
    fontSize: 12,
    fontWeight: '800',
  },
  xpPill: {
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  xpPillText: {
    color: '#D97706',
    fontSize: 12,
    fontWeight: '800',
  },
  quizMainTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: colors.ink,
    letterSpacing: -0.4,
    marginTop: 4,
  },
  quizStepCounter: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.muted,
    marginTop: 2,
    marginBottom: 10,
  },
  progressContainer: {
    height: 8,
    backgroundColor: '#E2E8F0',
    borderRadius: radius.pill,
    overflow: 'hidden',
    width: '100%',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: '#0095F6',
    borderRadius: radius.pill,
  },
  questionCard: {
    marginTop: spacing.sm,
    padding: spacing.lg,
  },
  questionPrompt: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.ink,
    lineHeight: 25,
    marginBottom: spacing.lg,
  },
  optionsList: {
    gap: 12,
    marginBottom: spacing.md,
  },
  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  optionCardPressed: {
    backgroundColor: '#F1F5F9',
    transform: [{ scale: 0.99 }],
  },
  optionCardSelected: {
    borderColor: '#0095F6',
    backgroundColor: '#EFF6FF',
  },
  optionCardCorrect: {
    borderColor: '#10B981',
    backgroundColor: '#ECFDF5',
  },
  optionCardWrong: {
    borderColor: '#EF4444',
    backgroundColor: '#FEF2F2',
  },
  optionLetterBadge: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: '#E2E8F0',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  optionLetterBadgeSelected: {
    backgroundColor: '#0095F6',
  },
  optionLetterBadgeCorrect: {
    backgroundColor: '#10B981',
  },
  optionLetterBadgeWrong: {
    backgroundColor: '#EF4444',
  },
  optionLetterText: {
    color: '#475569',
    fontSize: 14,
    fontWeight: '800',
  },
  optionLetterTextActive: {
    color: '#FFFFFF',
  },
  optionLabel: {
    flex: 1,
    color: colors.ink,
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 21,
  },
  optionLabelSelected: {
    color: '#0095F6',
    fontWeight: '700',
  },
  optionLabelCorrect: {
    color: '#065F46',
    fontWeight: '700',
  },
  optionLabelWrong: {
    color: '#991B1B',
    fontWeight: '700',
  },
  optionEndIcon: {
    marginLeft: 8,
  },
  feedbackContainer: {
    marginTop: spacing.sm,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
  },
  feedbackOk: {
    backgroundColor: '#ECFDF5',
    borderColor: '#A7F3D0',
  },
  feedbackInfo: {
    backgroundColor: '#EFF6FF',
    borderColor: '#BFDBFE',
  },
  feedbackText: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  feedbackTextOk: {
    color: '#065F46',
  },
  feedbackTextInfo: {
    color: '#1E40AF',
  },
});
