import Svg, { Circle, Path, Text } from 'react-native-svg';
import type { StyleProp, ViewStyle } from 'react-native';

/**
 * The exact LittleNet wordmark from the Stitch design kit:
 * bold system "LittleNet" in #262626 with the #0095F6 dot + arc accent.
 * viewBox is 200x48; pass width and the height scales automatically.
 */
export function LnWordmark({
  width = 132,
  style,
}: {
  width?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const height = (width * 48) / 200;
  return (
    <Svg width={width} height={height} viewBox="0 0 200 48" style={style}>
      <Text
        x={6}
        y={34}
        fontSize={28}
        fontWeight="700"
        fill="#262626"
        letterSpacing={-0.8}
      >
        LittleNet
      </Text>
      <Circle cx={128} cy={18} r={4} fill="#0095F6" />
      <Path
        d="M142 28 C145 22, 153 22, 156 28"
        stroke="#0095F6"
        strokeWidth={2.5}
        strokeLinecap="round"
        fill="none"
      />
    </Svg>
  );
}
