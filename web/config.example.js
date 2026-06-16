/**
 * Copy to config.js and configure for live agent mode:
 *   cp config.example.js config.js
 */
window.AGENT_CONFIG = {
  useLiveAgents: false,
  proxyBase: "http://127.0.0.1:3000",
  teamId: "team-web-demo",
  sessionId: "session-1",
  zalopay: {
    providerName: "Zalopay (Zion)",
    bankCode: "ZLP",
    bankBin: "",
    brandColor: "#0033c9",
  },
  endpoints: {
    weather: "https://endpoint-f84375b6-98f9-456c-9a9c-d38a4724ddaa.agentbase-runtime.aiplatform.vngcloud.vn",
    trip: "https://endpoint-e1287e38-7a87-4aea-a5cf-19762fe9179c.agentbase-runtime.aiplatform.vngcloud.vn",
    bill: "https://endpoint-5ca9ea82-4d2a-4526-be86-b731ea37355d.agentbase-runtime.aiplatform.vngcloud.vn",
  },
};
