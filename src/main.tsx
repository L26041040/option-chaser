import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { redirectToCanonicalIfNoIdentity } from "./canonicalHost";
import { initSentry } from "./observability";
import "./styles.css";

initSentry();

// #362：別名網址上沒有既有身分的新訪客先轉去正式網址，再決定要不要掛載 App。
// 其他網址（正式網址、Preview、部署專屬網址、localhost）立即回 false。
redirectToCanonicalIfNoIdentity().then((redirected) => {
  if (redirected) return;
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
