# CopyTrader — mobile app (React Native / Expo)

A thin React Native shell that shows the live terminal dashboard in a full-screen
WebView. View-only, paper account — no trading from the phone.

## Two ways to get the terminal on your phone

### A) PWA (no build, works today) — recommended
The dashboard is already an installable web app. On your phone, open the server URL
in the browser and **Add to Home Screen**:
- iPhone (Safari): Share → **Add to Home Screen**
- Android (Chrome): menu → **Install app** / **Add to Home screen**

You get an app icon that opens full-screen. To use it **anywhere** (not just home
Wi-Fi), the server must be publicly hosted — deploy this repo to Railway/Oracle and
use that public URL.

### B) This React Native app (literal native app)
1. Install Node + the Expo CLI, then in this folder:
   ```bash
   npm install
   ```
2. Edit `App.js` → set `SERVER_URL` to your hosted dashboard URL
   (e.g. `https://trialbot.up.railway.app`). For same-Wi-Fi testing use your Mac's
   LAN IP, e.g. `http://192.168.0.119:8787`.
3. Run it:
   ```bash
   npx expo start
   ```
   Scan the QR code with the **Expo Go** app on your phone — the terminal loads.

To ship a standalone installable build later: `npx eas build -p ios` / `-p android`.

## Note
Both options point at the same hosted server, so a `git push` that your server
auto-deploys (e.g. Railway) updates what the app shows — no app rebuild needed.
