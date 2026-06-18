// React Native (Expo) shell for the copy-trader terminal.
// It loads the live dashboard in a full-screen WebView, so the phone app always
// shows exactly what the server renders. Point SERVER_URL at your hosted dashboard
// (Railway/Oracle public URL) to use it anywhere; for same-Wi-Fi testing use your
// Mac's LAN IP. Paper only — view-only, no trading from the phone.
import React from 'react';
import { SafeAreaView, StatusBar, StyleSheet } from 'react-native';
import { WebView } from 'react-native-webview';

// CHANGE THIS to your public server URL once hosted (e.g. https://trialbot.up.railway.app)
const SERVER_URL = 'http://192.168.0.119:8787';

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" />
      <WebView
        source={{ uri: SERVER_URL }}
        style={styles.web}
        originWhitelist={['*']}
        pullToRefreshEnabled
        startInLoadingState
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000' },
  web: { flex: 1, backgroundColor: '#000000' },
});
