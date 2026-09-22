import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type AuthStackParamList = {
  Welcome: undefined;
  Login: { mode?: 'kids' | 'parent' | 'admin' } | undefined;
  ForgotPassword: undefined;
  ResetPassword: { userId: number; maskedEmail: string; message?: string };
  ParentRegister: undefined;
  OtpVerify: { pendingToken: string; emailSent?: boolean; devCode?: string };
  FaceLogin: { mode?: 'kids' } | undefined;
};

export type ChildStackParamList = {
  FaceEnroll: undefined;
  Quiz: { returnTo?: string } | undefined;
  KidsTabs: { tab?: string; createKind?: 'post' | 'reel' | 'story' } | undefined;
  FeedTab: undefined;
  DiscoverTab: undefined;
  CreateTab: { kind?: 'post' | 'reel' | 'story' } | undefined;
  ReelsTab: undefined;
  ProfileTab: undefined;
  Stories: undefined;
  NotificationsTab: undefined;
  Conversations: undefined;
  Chat: { peerId: number; postId?: number };
  ChatDetails: { peerId: number };
  NewMessage: undefined;
  SavedContent: undefined;
  EditProfile: undefined;
  Connections: { mode?: 'followers' | 'following' } | undefined;
  PostDetail: { postId: number };
  SafetyCentre: undefined;
  ReportHistory: undefined;
  OtherProfile: { targetId: number };
  ProcessingStatus: { postId: number };
};

export type ParentStackParamList = {
  ParentHome: undefined;
  Children: undefined;
  ChildSummary: { childId: number };
  CreateChild: undefined;
  ParentSafety: undefined;
  ParentReview: { eventId: number };
  ScreenTime: { childId?: number } | undefined;
  ParentControls: { childId?: number } | undefined;
  FollowRequests: undefined;
  ParentActivity: { childId?: number } | undefined;
  ParentNotifications: undefined;
  ParentSettings: undefined;
};

export type AdminStackParamList = {
  AdminHome: undefined;
  AdminReviews: undefined;
  AdminReview: { eventId: number };
  AdminUsers: undefined;
  AdminAudit: undefined;
};

export type AuthScreenProps<Route extends keyof AuthStackParamList> = NativeStackScreenProps<AuthStackParamList, Route>;
export type ChildScreenProps<Route extends keyof ChildStackParamList> = NativeStackScreenProps<ChildStackParamList, Route>;
export type ParentScreenProps<Route extends keyof ParentStackParamList> = NativeStackScreenProps<ParentStackParamList, Route>;
export type AdminScreenProps<Route extends keyof AdminStackParamList> = NativeStackScreenProps<AdminStackParamList, Route>;
