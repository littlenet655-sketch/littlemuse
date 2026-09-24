import { useCallback, useEffect, useState } from 'react';
import { NavigationContainer, useIsFocused, useNavigation } from '@react-navigation/native';
import type { NavigationProp } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../auth/AuthProvider';
import { KidsTabsHost } from '../screens/kids/KidsTabsHost';
import { FeedScreen } from '../screens/kids/FeedScreen';
import { StoriesScreen } from '../screens/kids/StoriesScreen';
import { ReelsScreen } from '../screens/kids/ReelsScreen';
import { DiscoverScreen } from '../screens/kids/DiscoverScreen';
import { OwnProfileScreen } from '../screens/kids/OwnProfileScreen';
import { OtherProfileScreen } from '../screens/kids/OtherProfileScreen';
import { PostDetailScreen } from '../screens/kids/PostDetailScreen';
import { ScreenTimeLockedScreen } from '../screens/kids/ScreenTimeLockedScreen';
import { NotificationsScreen } from '../screens/kids/NotificationsScreen';
import { ConversationsScreen } from '../screens/kids/ConversationsScreen';
import { ChatScreen } from '../screens/kids/ChatScreen';
import { ChatDetailsScreen, ConnectionsScreen, EditProfileScreen, NewMessageScreen, SavedContentScreen } from '../screens/kids/SocialStates';
import { CreateScreen } from '../screens/kids/CreateScreen';
import { ProcessingStatusScreen } from '../screens/kids/ProcessingScreen';
import { SafetyCentreScreen, ReportHistoryScreen } from '../screens/kids/SafetyScreens';
import { CreateChildScreen } from '../screens/Parent';
import {
  ParentActivityScreen,
  ParentChildSummaryScreen,
  ParentChildrenScreen,
  ParentControlsScreen,
  ParentFollowRequestsScreen,
  ParentHomeScreen,
  ParentNotificationsScreen,
  ParentReviewScreen,
  ParentSafetyScreen,
  ParentScreenTimeScreen,
  ParentSettingsScreen,
} from '../screens/parent/ParentScreens';
import {
  AdminAuditScreen,
  AdminHomeScreen,
  AdminReviewScreen,
  AdminReviewsScreen,
  AdminUsersScreen,
} from '../screens/admin/AdminScreens';
import { OtpVerifyScreen, ParentRegisterScreen } from '../screens/ParentOnboarding';
import { ForgotPasswordScreen, ResetPasswordScreen } from '../screens/PasswordReset';
import { QuizScreen } from '../screens/Quiz';
import { LoginScreen, WelcomeScreen } from '../screens/WelcomeLogin';
import { BrandHeader, Button, LoadingState, Notice, Screen } from '../ui/components';
import { ParentModeGate } from '../components/ParentModeGate';
import { useScreenTimeHeartbeat } from '../kids/useScreenTimeHeartbeat';
import { resolveChildRoute } from './gates';
import type { AdminStackParamList, AuthStackParamList, ChildStackParamList, ParentStackParamList } from './types';
import { colors } from '../ui/tokens';

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const ChildStack = createNativeStackNavigator<ChildStackParamList>();
const ParentStack = createNativeStackNavigator<ParentStackParamList>();
const AdminStack = createNativeStackNavigator<AdminStackParamList>();

const cleanStackOptions = {
  headerShadowVisible: false,
  headerStyle: { backgroundColor: colors.background },
  headerTintColor: colors.ink,
  headerTitleStyle: { fontWeight: '800' as const },
};

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={cleanStackOptions}>
      <AuthStack.Screen name="Welcome" component={WelcomeScreen} options={{ headerShown: false }} />
      <AuthStack.Screen name="Login" component={LoginScreen} options={{ headerTitle: '' }} />
      <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} options={{ headerTitle: '' }} />
      <AuthStack.Screen name="ResetPassword" component={ResetPasswordScreen} options={{ headerTitle: '' }} />
      <AuthStack.Screen name="ParentRegister" component={ParentRegisterScreen} options={{ headerTitle: '' }} />
      <AuthStack.Screen name="OtpVerify" component={OtpVerifyScreen} options={{ headerTitle: '' }} />
    </AuthStack.Navigator>
  );
}

/**
 * Keeps the visible child screen pinned to the authoritative gate state.
 * Runs on mount (fixes any initial-route mismatch) and on every gate change,
 * so enrollment/quiz completion transitions without manual navigation.
 */
function ChildGateSync() {
  const navigation = useNavigation<NavigationProp<ChildStackParamList>>();
  const focused = useIsFocused();
  const { session } = useAuth();

  useEffect(() => {
    if (!focused) return;
    const timer = setTimeout(() => {
      try {
        const state = navigation.getState();
        const index = state?.index ?? 0;
        const current = state?.routes[index]?.name as keyof ChildStackParamList | undefined;
        if (!current) return;
        const target = resolveChildRoute(session?.onboarding, session?.user.quiz_required ?? true, current);
        if (current === target) return;
        navigation.reset({
          index: 0,
          routes: [{ name: target } as never],
        });
      } catch {
        // Suppress unhandled reset during mid-transition unmount
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [focused, navigation, session?.onboarding, session?.user.quiz_required]);

  return null;
}

function ChildNavigator() {
  const { session, signOut } = useAuth();
  const [activeLock, setActiveLock] = useState<string | null>(null);
  const handleGateChange = useCallback((gate: string | null) => setActiveLock(gate), []);
  useScreenTimeHeartbeat(handleGateChange);

  const initialRoute = resolveChildRoute(
    session?.onboarding,
    session?.user.quiz_required ?? true,
    'KidsTabs',
  );

  if (activeLock) {
    return (
      <ScreenTimeLockedScreen
        lockType={activeLock === 'quiet_hours' ? 'quiet_hours' : 'screen_time'}
        onUnlock={() => setActiveLock(null)}
        onSignOut={() => void signOut()}
      />
    );
  }

  return (
    <ChildStack.Navigator initialRouteName={initialRoute} screenOptions={cleanStackOptions}>
      <ChildStack.Screen name="Quiz" component={withGateSync(QuizScreen)} options={{ title: 'Safety quiz' }} />
      <ChildStack.Screen name="KidsTabs" component={withGateSync(KidsTabsHost)} options={{ headerShown: false }} />
      <ChildStack.Screen name="FeedTab" component={withGateSync(FeedScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="DiscoverTab" component={withGateSync(DiscoverScreen)} options={{ title: 'Discover' }} />
      <ChildStack.Screen name="CreateTab" component={withGateSync(CreateScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="ReelsTab" component={withGateSync(ReelsScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="ProfileTab" component={withGateSync(OwnProfileScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="Stories" component={withGateSync(StoriesScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="NotificationsTab" component={withGateSync(NotificationsScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="Conversations" component={withGateSync(ConversationsScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="Chat" component={withGateSync(ChatScreen)} options={{ headerShown: false }} />
      <ChildStack.Screen name="ChatDetails" component={withGateSync(ChatDetailsScreen)} options={{ title: 'Chat details' }} />
      <ChildStack.Screen name="NewMessage" component={withGateSync(NewMessageScreen)} options={{ title: 'New message' }} />
      <ChildStack.Screen name="SavedContent" component={withGateSync(SavedContentScreen)} options={{ title: 'Saved' }} />
      <ChildStack.Screen name="EditProfile" component={withGateSync(EditProfileScreen)} options={{ title: 'Edit profile' }} />
      <ChildStack.Screen name="Connections" component={withGateSync(ConnectionsScreen)} options={{ title: 'Connections' }} />
      <ChildStack.Screen name="PostDetail" component={withGateSync(PostDetailScreen)} options={{ title: 'Post' }} />
      <ChildStack.Screen name="SafetyCentre" component={withGateSync(SafetyCentreScreen)} options={{ title: 'Safety Centre' }} />
      <ChildStack.Screen name="ReportHistory" component={withGateSync(ReportHistoryScreen)} options={{ title: 'Report history' }} />
      <ChildStack.Screen name="OtherProfile" component={withGateSync(OtherProfileScreen)} options={{ title: 'Profile' }} />
      <ChildStack.Screen name="ProcessingStatus" component={withGateSync(ProcessingStatusScreen)} options={{ headerShown: false }} />
    </ChildStack.Navigator>
  );
}

/** Mounts the gate sync inside the active child screen (navigators accept only Screens). */
function withGateSync(Component: React.ComponentType<any>): React.ComponentType<any> {
  return function GatedScreen(props: any) {
    return (
      <>
        <ChildGateSync />
        <Component {...props} />
      </>
    );
  };
}

function ParentNavigator() {
  return (
    <ParentStack.Navigator initialRouteName="ParentHome" screenOptions={cleanStackOptions}>
      <ParentStack.Screen name="ParentHome" component={ParentHomeScreen} options={{ title: 'Parent dashboard' }} />
      <ParentStack.Screen name="Children" component={ParentChildrenScreen} options={{ title: 'Children' }} />
      <ParentStack.Screen name="ChildSummary" component={ParentChildSummaryScreen} options={{ title: 'Child summary' }} />
      <ParentStack.Screen name="CreateChild" component={CreateChildScreen} options={{ title: 'Add a child' }} />
      <ParentStack.Screen name="ParentSafety" component={ParentSafetyScreen} options={{ title: 'Safety review' }} />
      <ParentStack.Screen name="ParentReview" component={ParentReviewScreen} options={{ title: 'Review detail' }} />
      <ParentStack.Screen name="ScreenTime" component={ParentScreenTimeScreen} options={{ title: 'Screen time' }} />
      <ParentStack.Screen name="ParentControls" component={ParentControlsScreen} options={{ title: 'Controls' }} />
      <ParentStack.Screen name="FollowRequests" component={ParentFollowRequestsScreen} options={{ title: 'Follow requests' }} />
      <ParentStack.Screen name="ParentActivity" component={ParentActivityScreen} options={{ title: 'Activity' }} />
      <ParentStack.Screen name="ParentNotifications" component={ParentNotificationsScreen} options={{ title: 'Notifications' }} />
      <ParentStack.Screen name="ParentSettings" component={ParentSettingsScreen} options={{ title: 'Settings' }} />
    </ParentStack.Navigator>
  );
}

function AdminNavigator() {
  return (
    <AdminStack.Navigator screenOptions={cleanStackOptions}>
      <AdminStack.Screen name="AdminHome" component={AdminHomeScreen} options={{ title: 'Moderation' }} />
      <AdminStack.Screen name="AdminReviews" component={AdminReviewsScreen} options={{ title: 'Moderation queue' }} />
      <AdminStack.Screen name="AdminReview" component={AdminReviewScreen} options={{ title: 'Review detail' }} />
      <AdminStack.Screen name="AdminUsers" component={AdminUsersScreen} options={{ title: 'User lookup' }} />
      <AdminStack.Screen name="AdminAudit" component={AdminAuditScreen} options={{ title: 'Audit history' }} />
    </AdminStack.Navigator>
  );
}

/**
 * Role-aware cold-start routing: unauthenticated -> AuthStack, CHILD ->
 * ChildStack (reactively forced to quiz only while a gate is active),
 * PARENT -> ParentStack, ADMIN -> AdminStack.
 */
export function RootNavigator() {
  const { status, session } = useAuth();

  if (status === 'loading') {
    return (
      <Screen hasNativeHeader={false}>
        <LoadingState message="Starting LittleNet…" />
      </Screen>
    );
  }

  if (status === 'signedOut' || !session) {
    return (
      <NavigationContainer>
        <AuthNavigator />
      </NavigationContainer>
    );
  }

  if (session.user.role === 'PARENT') {
    return (
      <NavigationContainer>
        <ParentModeGate>
          <ParentNavigator />
        </ParentModeGate>
      </NavigationContainer>
    );
  }

  if (session.user.role === 'ADMIN') {
    return (
      <NavigationContainer>
        <AdminNavigator />
      </NavigationContainer>
    );
  }

  return (
    <NavigationContainer>
      <ChildNavigator />
    </NavigationContainer>
  );
}
