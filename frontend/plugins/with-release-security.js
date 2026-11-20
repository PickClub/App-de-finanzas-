const { withAndroidManifest } = require('expo/config-plugins');
module.exports = config => withAndroidManifest(config, config => {
  const application = config.modResults.manifest.application[0];
  application.$['android:usesCleartextTraffic'] = 'false';
  application.$['android:allowBackup'] = 'false';
  return config;
});
