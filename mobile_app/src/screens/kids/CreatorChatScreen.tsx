import { useCallback, useEffect, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { fetchCreatorChat, sendCreatorChat, type CreatorChatMessage } from '../../api/creatorChat';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { ErrorState, LoadingState, Screen } from '../../ui/components';
import { colors } from '../../ui/tokens';

export function CreatorChatScreen({ route, navigation }: ChildScreenProps<'CreatorChat'>) {
  const { session } = useAuth();
  const creatorId = Number(route.params.creatorId);
  const [creatorName, setCreatorName] = useState(route.params.displayName || 'Learning creator');
  const [vertical, setVertical] = useState(route.params.vertical || '');
  const [messages, setMessages] = useState<CreatorChatMessage[]>([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    if (!session?.token || !creatorId) return;
    try {
      setError(null);
      const res = await fetchCreatorChat(session.token, creatorId);
      setCreatorName(res.creator.display_name || creatorName);
      setVertical(res.creator.interest_vertical || vertical);
      setMessages(res.messages || []);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [session?.token, creatorId]);

  useEffect(() => { void load(); }, [load]);

  async function send() {
    const value = text.trim();
    if (!value || !session?.token || sending) return;
    setSending(true);
    setText('');
    try {
      const res = await sendCreatorChat(session.token, creatorId, value);
      setMessages(res.messages || []);
    } catch (e) {
      setError(e);
      setText(value);
    } finally {
      setSending(false);
    }
  }

  return (
    <Screen hasNativeHeader={false} contentStyle={styles.screen}>
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={8} accessibilityRole="button" accessibilityLabel="Back">
          <Feather name="arrow-left" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.headerText}>
          <Text style={styles.title}>{creatorName}</Text>
          <Text style={styles.subtitle}>{vertical || 'LittleNet learning creator'}</Text>
        </View>
        <Feather name="book-open" size={20} color={colors.brand} />
      </View>

      {loading ? <LoadingState message="Opening learning chat…" /> : error && messages.length === 0 ? <ErrorState onRetry={() => void load()} /> : (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <FlatList
            data={messages}
            keyExtractor={(m) => String(m.message_id)}
            contentContainerStyle={styles.list}
            renderItem={({ item }) => {
              const mine = item.sender === 'CHILD';
              return (
                <View style={[styles.bubble, mine ? styles.mine : styles.creator]}>
                  <Text style={[styles.message, mine && styles.mineText]}>{item.message_text}</Text>
                </View>
              );
            }}
            ListEmptyComponent={<Text style={styles.empty}>Ask {creatorName} something about {vertical || 'their learning topic'}.</Text>}
          />
          <View style={styles.composer}>
            <TextInput
              value={text}
              onChangeText={setText}
              placeholder={vertical ? `Ask about ${vertical}…` : 'Ask a learning question…'}
              style={styles.input}
              multiline
              maxLength={500}
            />
            <Pressable style={styles.send} onPress={() => void send()} disabled={!text.trim() || sending} accessibilityRole="button" accessibilityLabel="Send">
              <Feather name="send" size={18} color="#FFFFFF" />
            </Pressable>
          </View>
          {error && messages.length ? <Text style={styles.error}>That message could not be sent. Try again.</Text> : null}
        </KeyboardAvoidingView>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: 0, paddingBottom: 0 },
  flex: { flex: 1 },
  header: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: colors.line },
  headerText: { flex: 1 },
  title: { fontSize: 16, fontWeight: '800', color: colors.ink },
  subtitle: { fontSize: 12, color: colors.muted, marginTop: 2 },
  list: { padding: 16, gap: 10, flexGrow: 1 },
  bubble: { maxWidth: '84%', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 10 },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.brand },
  creator: { alignSelf: 'flex-start', backgroundColor: '#F3F4F6' },
  message: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  mineText: { color: '#FFFFFF' },
  empty: { textAlign: 'center', color: colors.muted, marginTop: 48, paddingHorizontal: 24 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: colors.line },
  input: { flex: 1, minHeight: 42, maxHeight: 110, borderWidth: 1, borderColor: colors.line, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10, color: colors.ink },
  send: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  error: { color: '#B91C1C', fontSize: 12, paddingHorizontal: 16, paddingBottom: 8 },
});
