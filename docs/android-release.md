# Android release

The native Capacitor shell lives in `web/android`. It loads the same-origin
production site at `https://it.rainstone.top`, so the existing HttpOnly session
cookie, readable CSRF cookie, multipart uploads, and SSE behavior remain intact.

- Application name: `技术面试`
- Application ID: `top.rainstone.technicalinterviewagent`
- Version: `versionName=0.1.0`, `versionCode=1`
- Minimum SDK: 26
- Compile SDK: 36; target SDK: 35

## Local debug build

Install JDK 21 and Android SDK platform 36, then run:

```bash
cd web
npm ci
npm run build
npx cap sync android
cd android
./gradlew assembleDebug
```

The debug APK is
`web/android/app/build/outputs/apk/debug/app-debug.apk`. It uses the standard
debug key and the `.debug` application ID suffix. Install it with:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Release signing

Create a release keystore outside the repository and keep it in a secret
manager. Never commit the keystore or passwords:

```bash
keytool -genkeypair -v -keystore /secure/path/interview-release.p12 \
  -storetype PKCS12 -alias interview-release \
  -keyalg RSA -keysize 4096 -validity 10000
```

Export the four signing variables only for the build:

```bash
export ANDROID_KEYSTORE_PATH=/secure/path/interview-release.p12
export ANDROID_KEYSTORE_PASSWORD='...'
export ANDROID_KEY_ALIAS=interview-release
export ANDROID_KEY_PASSWORD='...'
cd web/android
./gradlew bundleRelease assembleRelease
```

Missing signing variables fail the release task. The outputs are
`app/build/outputs/bundle/release/app-release.aab` and
`app/build/outputs/apk/release/app-release.apk`.

## GitHub Actions

The `android` workflow builds and tests debug artifacts on pull requests. A
tag matching `v*` builds signed release artifacts and uploads both files plus
checksums to GitHub Release.

Configure these repository secrets:

- `ANDROID_KEYSTORE_BASE64`: base64-encoded PKCS12 keystore
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Create and push a release tag:

```bash
git tag -a v0.1.0 -m "Android v0.1.0"
git push origin v0.1.0
```

## Verification and store submission

Verify the APK signature and checksum:

```bash
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
shasum -a 256 app/build/outputs/apk/release/app-release.apk \
  app/build/outputs/bundle/release/app-release.aab
```

Google Play Console submission is intentionally manual: upload the signed AAB,
complete data safety and content-rating forms, configure the app signing key,
add store listing assets, and submit the release for review. These actions
require the project owner's Play Console account and approvals and cannot be
performed by this repository workflow.
