// Expo replaces these explicit property references in the embedded release bundle.
const { resolveTarget } = require('./release-policy.cjs') as {
  resolveTarget: (input: { environment?: string; origin?: string; auth: boolean; release: boolean; environmentId?: string }) => {
    environment: string; origin: string; environmentId: string; auth: boolean; storageKey: string;
  };
};
const environment = process.env.EXPO_PUBLIC_APP_ENV || 'development';
export const authenticationRequired = !__DEV__ || environment !== 'development' || process.env.EXPO_PUBLIC_R3_AUTH === '1';
export function apiTarget() {
  return resolveTarget({ environment, origin: process.env.EXPO_PUBLIC_BACKEND_URL,
    environmentId: process.env.EXPO_PUBLIC_API_ENVIRONMENT_ID,
    auth: process.env.EXPO_PUBLIC_R3_AUTH === '1', release: !__DEV__ });
}
