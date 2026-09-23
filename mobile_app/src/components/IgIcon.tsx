import Svg, { Circle, Path, Polygon, Rect } from 'react-native-svg';
import type { StyleProp, ViewStyle } from 'react-native';

/**
 * Kit-exact Instagram-style icons from the Stitch design kit.
 * Path data is copied verbatim from the kit's feed mockup bottom-nav
 * and post-action sections — do not "improve" them.
 */
export type IgIconName =
  | 'home-outline'
  | 'home-filled'
  | 'search'
  | 'create'
  | 'reels'
  | 'heart'
  | 'heart-filled'
  | 'comment'
  | 'send'
  | 'bookmark'
  | 'bookmark-filled'
  | 'more-horizontal'
  | 'verified';

interface IgIconProps {
  name: IgIconName;
  size?: number;
  color?: string;
  style?: StyleProp<ViewStyle>;
}

const STROKE_DEFAULT = 1.9;

export function IgIcon({ name, size = 24, color = '#262626', style }: IgIconProps) {
  const strokeProps = {
    fill: 'none' as const,
    stroke: color,
    strokeWidth: STROKE_DEFAULT,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" style={style}>
      {name === 'home-outline' && (
        <Path d="M3 10.8 12 3l9 7.8v9.2a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" {...strokeProps} />
      )}
      {name === 'home-filled' && <Path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" fill={color} />}
      {name === 'search' && (
        <Path
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          {...strokeProps}
          strokeWidth={2.2}
        />
      )}
      {name === 'create' && (
        <>
          <Rect x={3} y={3} width={18} height={18} rx={5} {...strokeProps} strokeWidth={2} />
          <Path d="M12 8v8M8 12h8" {...strokeProps} strokeWidth={2} />
        </>
      )}
      {name === 'reels' && (
        <>
          <Rect x={2} y={3} width={20} height={18} rx={4} {...strokeProps} />
          <Path d="M2 9h20M7 3l3 6M14 3l3 6" {...strokeProps} />
          <Polygon points="10,12 10,17 15,14.5" fill={color} stroke="none" />
        </>
      )}
      {name === 'heart' && (
        <Path
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
          {...strokeProps}
          strokeWidth={1.8}
        />
      )}
      {name === 'heart-filled' && (
        <Path
          d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
          fill={color}
        />
      )}
      {name === 'comment' && (
        <Path
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          {...strokeProps}
          strokeWidth={1.8}
        />
      )}
      {name === 'send' && (
        <Path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" {...strokeProps} strokeWidth={1.8} />
      )}
      {name === 'bookmark' && (
        <Path
          d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
          {...strokeProps}
          strokeWidth={1.8}
        />
      )}
      {name === 'bookmark-filled' && (
        <Path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" fill={color} />
      )}
      {name === 'more-horizontal' && (
        <>
          <Circle cx={5} cy={12} r={1.7} fill={color} />
          <Circle cx={12} cy={12} r={1.7} fill={color} />
          <Circle cx={19} cy={12} r={1.7} fill={color} />
        </>
      )}
      {name === 'verified' && (
        <Path
          d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1.2 14.2l-3.5-3.5 1.41-1.41 2.09 2.08 5.66-5.65 1.41 1.41-7.07 7.07z"
          fill={color}
        />
      )}
    </Svg>
  );
}
