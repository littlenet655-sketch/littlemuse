/**
 * LittleNet mobile root.
 *
 * Composition: safe-area → server-state (QueryProvider) → session/auth
 * (AuthProvider) → role-aware navigation (RootNavigator).
 *
 * Splash behaviour:
 *  - preventAutoHideAsync() keeps the native splash up while JS loads.
 *  - Once AuthProvider resolves its loading state, the native splash is
 *    hidden and the in-app animated logo fades out to reveal the app.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  Image,
  StyleSheet,
} from 'react-native';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from './src/auth/AuthProvider';
import { RootNavigator } from './src/navigation/RootNavigator';
import { QueryProvider } from './src/query/client';
import { installParentGateInvalidation } from './src/deviceAuth/parentAuthGate';

// Keep native splash visible until we are ready to reveal the app.
SplashScreen.preventAutoHideAsync().catch(() => {});

/** Animated logo overlay that sits on top of the app during auth load. */
function SplashOverlay({ onReady }: { onReady: () => void }) {
  const { status } = useAuth();
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(0.85)).current;
  const [hidden, setHidden] = useState(false);

  // Entrance pop-in when the overlay first mounts
  useEffect(() => {
    Animated.spring(scale, {
      toValue: 1,
      friction: 6,
      tension: 60,
      useNativeDriver: true,
    }).start();
  }, [scale]);

  // Once auth resolves, hide native splash then fade out the in-app overlay
  useEffect(() => {
    if (status === 'loading') return;
    void SplashScreen.hideAsync().catch(() => {});
    onReady();
    Animated.timing(opacity, {
      toValue: 0,
      duration: 350,
      useNativeDriver: true,
    }).start(() => setHidden(true));
  }, [status, opacity, onReady]);

  if (hidden) return null;

  return (
    <Animated.View style={[styles.splash, { opacity }]} pointerEvents="none">
      <Animated.View style={{ transform: [{ scale }] }}>
        <Image
          source={require('./assets/app_logo.png')}
          style={styles.logo}
          resizeMode="contain"
        />
      </Animated.View>
    </Animated.View>
  );
}

export default function App() {
  const [appReady, setAppReady] = useState(false);
  const handleReady = useCallback(() => setAppReady(true), []);

  // Install the parent-auth background invalidation once at startup.
  // Idempotent: the ParentModeGate also installs it on mount.
  useEffect(() => {
    const remove = installParentGateInvalidation();
    return remove;
  }, []);

  return (
    <SafeAreaProvider>
      <QueryProvider>
        <AuthProvider>
          {/* Render the navigator immediately — it handles its own loading state.
              The SplashOverlay sits on top and fades out once auth settles. */}
          <RootNavigator />
          <SplashOverlay onReady={handleReady} />
        </AuthProvider>
      </QueryProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  splash: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#FFF9F2',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 9999,
  },
  logo: {
    width: 160,
    height: 160,
  },
});
