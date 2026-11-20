// Shared build/runtime policy. Public configuration is never a secret container.
function resolveTarget({ environment = 'development', origin = '', auth = false, release = false, environmentId = '' }) {
  if (!['development', 'test', 'production'].includes(environment)) throw Error('Invalid application environment');
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  if (release && environment === 'development') throw Error('Development configuration cannot run in a release');
  if (environment !== 'development') {
    let url;
    try { url = new URL(origin); } catch { throw Error('Explicit HTTPS API origin required'); }
    if (!auth || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
        url.pathname !== '/' || origin !== url.origin || url.port ||
        !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(url.hostname) ||
        /(?:^|\.)(?:localhost|local|internal|test|invalid)$/.test(url.hostname) || !uuid.test(environmentId)) {
      throw Error('Authenticated HTTPS API and environment identity required');
    }
  } else if (auth && origin !== 'http://127.0.0.1:8013') {
    throw Error('Local authentication requires the authorized synthetic API');
  }
  return { environment, origin, environmentId, auth, storageKey: environment === 'development'
    ? 'moneyflow.r3.local.refresh.v1' : `pickwallet.${environment}.${environmentId}.refresh.v1` };
}
module.exports = { resolveTarget };
