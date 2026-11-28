import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

/**
 * Clean, premium LittleNet wordmark for the header.
 * Uses crisp native typography in #262626 with bold styling,
 * eliminating detached vector artifacts that look like frozen loaders.
 */
export function LnWordmark({
  width = 132,
  style,
}: {
  width?: number;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.wrap, style]}>
      <Text style={styles.text} accessibilityRole="header">
        LittleNet
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    justifyContent: 'center',
    paddingVertical: 2,
  },
  text: {
    fontSize: 25,
    fontWeight: '800',
    color: '#262626',
    letterSpacing: -0.6,
  },
});
