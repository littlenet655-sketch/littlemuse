import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { KidsTabsShell } from './KidsTabs';
import { useKidsHydration } from '../../kids/useKidsHydration';
import { FeedScreen } from './FeedScreen';
import { DiscoverScreen } from './DiscoverScreen';
import { CreateScreen } from './CreateScreen';
import { ReelsScreen } from './ReelsScreen';
import { OwnProfileScreen } from './OwnProfileScreen';

export function KidsTabsHost(props: ChildScreenProps<'KidsTabs'>) {
  const { signOut } = useAuth();
  useKidsHydration();
  const tab = String((props.route.params as { tab?: string } | undefined)?.tab ?? 'FeedTab');
  return (
    <KidsTabsShell
      navigation={props.navigation}
      route={props.route}
      render={(active) => (
        <>
          {active === 'DiscoverTab' ? <DiscoverScreen navigation={props.navigation} route={{ ...props.route, name: 'DiscoverTab' } as never} /> : null}
          {active === 'CreateTab' ? <CreateScreen navigation={props.navigation as never} route={{ ...props.route, name: 'CreateTab', params: undefined } as never} /> : null}
          {active === 'ReelsTab' ? <ReelsScreen navigation={props.navigation} route={{ ...props.route, name: 'ReelsTab' } as never} /> : null}
          {active === 'ProfileTab' ? <OwnProfileScreen navigation={props.navigation} route={{ ...props.route, name: 'ProfileTab' } as never} /> : null}
          {active !== 'DiscoverTab' && active !== 'CreateTab' && active !== 'ReelsTab' && active !== 'ProfileTab' ? <FeedScreen navigation={props.navigation} route={props.route} /> : null}
        </>
      )}
    />
  );
}
