const { resolveTarget } = require('./src/release-policy.cjs');
module.exports = ({ config }) => {
  const environment = process.env.EXPO_PUBLIC_APP_ENV || 'development';
  const release = !!process.env.EAS_BUILD_PROFILE && process.env.EAS_BUILD_PROFILE !== 'development';
  resolveTarget({ environment, origin: process.env.EXPO_PUBLIC_BACKEND_URL,
    environmentId: process.env.EXPO_PUBLIC_API_ENVIRONMENT_ID,
    auth: process.env.EXPO_PUBLIC_R3_AUTH === '1', release });
  const projectId = process.env.PW_EAS_PROJECT_ID;
  if (release && !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(projectId || '')) {
    throw Error('An approved EAS project ID is required for a release');
  }
  return { ...config, name: 'PickWallet', android: { ...config.android, versionCode: 1,
    allowBackup: false, permissions: [], blockedPermissions: [
      'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE',
      'android.permission.SYSTEM_ALERT_WINDOW', 'android.permission.RECORD_AUDIO',
      'android.permission.CAMERA', 'android.permission.READ_MEDIA_IMAGES',
      'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_MEDIA_AUDIO',
    ] }, plugins: [...(config.plugins || []), './plugins/with-release-security'],
    updates: { enabled: false },
    extra: { ...config.extra, ...(projectId ? { eas: { projectId } } : {}) } };
};
