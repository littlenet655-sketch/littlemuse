/**
 * Production Android builds must refuse cleartext HTTP.
 * Expo SDK 57 removed android.usesCleartextTraffic from the public app.json
 * schema; this plugin still writes the manifest attribute during prebuild.
 */
const { withAndroidManifest } = require('@expo/config-plugins');

function withCleartextDisabled(config) {
  return withAndroidManifest(config, (config) => {
    const application = config.modResults.manifest.application?.[0];
    if (application) {
      application.$['android:usesCleartextTraffic'] = 'false';
    }
    return config;
  });
}

module.exports = withCleartextDisabled;
