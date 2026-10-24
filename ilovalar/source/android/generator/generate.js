/* ITC Academy — Android TWA loyihasini Bubblewrap core bilan yaratadi.
   Ishlatish:  node generate.js <icon-base-url> <chiqish-papkasi> <keystore-yo'li>
   Masalan:    node generate.js http://127.0.0.1:8799/pwa/icons ../twa C:\Users\<siz>\.itc-academy-signing\itc-academy-release.jks
   icon-base-url — static/pwa/icons ni beruvchi manzil (production deploy'dan keyin: https://itc-academy.uz/static/pwa/icons). */
'use strict';
const path = require('path');
const fs = require('fs');
const { TwaManifest, TwaGenerator, ConsoleLog } = require('@bubblewrap/core');

const [iconBase, outDir, keystore] = process.argv.slice(2);
if (!iconBase || !outDir || !keystore) {
  console.error('Foydalanish: node generate.js <icon-base-url> <chiqish-papkasi> <keystore-yo\'li>');
  process.exit(2);
}

const HOST = 'itc-academy.uz';
const manifest = new TwaManifest({
  packageId: 'uz.itcacademy.lms',
  host: HOST,
  name: 'ITC Academy',
  launcherName: 'ITC Academy',
  display: 'standalone',
  themeColor: '#4F46E5',
  themeColorDark: '#0B1020',
  navigationColor: '#FFFFFF',
  navigationColorDark: '#0B1020',
  navigationDividerColor: '#FFFFFF',
  navigationDividerColorDark: '#0B1020',
  backgroundColor: '#FFFFFF',
  enableNotifications: false,
  startUrl: '/',
  iconUrl: `${iconBase}/icon-512.png`,
  maskableIconUrl: `${iconBase}/maskable-512.png`,
  splashScreenFadeOutDuration: 300,
  signingKey: { path: keystore, alias: 'itcacademy' },
  appVersionCode: 1,
  appVersion: '1.0.0',
  shortcuts: [],
  generatorApp: 'bubblewrap-core',
  fallbackType: 'customtabs',
  enableSiteSettingsShortcut: true,
  orientation: 'default',
  minSdkVersion: 24, // androidbrowserhelper 2.7.x talabi (Android 7.0+)
  fingerprints: [],
  additionalTrustedOrigins: [],
  retainedBundles: [],
});

(async () => {
  const target = path.resolve(outDir);
  fs.mkdirSync(target, { recursive: true });
  await new TwaGenerator().createTwaProject(target, manifest, new ConsoleLog('twa'));
  // Production manifest manzili (bubblewrap update uchun) va ikonkalar productiondagi manzilga yoziladi
  const json = manifest.toJson();
  json.webManifestUrl = `https://${HOST}/manifest.webmanifest`;
  json.iconUrl = `https://${HOST}/static/pwa/icons/icon-512.png`;
  json.maskableIconUrl = `https://${HOST}/static/pwa/icons/maskable-512.png`;
  fs.writeFileSync(path.join(target, 'twa-manifest.json'), JSON.stringify(json, null, 2) + '\n');
  console.log('TWA loyihasi yaratildi:', target);
})().catch((e) => { console.error(e); process.exit(1); });
