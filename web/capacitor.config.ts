import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "top.rainstone.technicalinterviewagent",
  appName: "技术面试",
  webDir: "dist",
  server: {
    url: "https://it.rainstone.top",
    cleartext: false,
    androidScheme: "https",
  },
  android: {
    allowMixedContent: false,
    captureInput: true,
    webContentsDebuggingEnabled: false,
  },
};

export default config;
