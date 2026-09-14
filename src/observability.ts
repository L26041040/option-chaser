/**
 * Sentry 錯誤上報接線（PB-13／#293，Anonymous Public Beta）。
 *
 * 未設定 `VITE_SENTRY_DSN` 時 `initSentry()` 直接回傳、不初始化
 * `@sentry/browser`——不改變任何既有行為（PB-13 Non-goals：
 * 「不得順手改動既有邏輯」）。
 *
 * PII scrubbing：`beforeSend` 丟掉 breadcrumb 裡任何 `Cookie` 標頭
 * 與請求 URL 的 query string（匿名身份 cookie token 不該隨錯誤堆疊
 * 上傳），並對 exception 訊息套用簡單的樣式遮蔽（承接
 * `api_app/diagnostics.py::_mask_patterns()` 的同一種「Bearer …／
 * token=…」偵測思路，前端這裡是獨立、輕量的字串替換，不共用後端
 * 模組——兩邊本來就是不同語言的獨立部署單位）。
 */
import * as Sentry from "@sentry/browser";

const SECRET_PATTERNS: RegExp[] = [
  /Bearer\s+[A-Za-z0-9._-]+/gi,
  /token=[^&\s]+/gi,
  /postgres(?:ql)?:\/\/[^\s]+/gi,
];

function scrubText(value: string): string {
  let out = value;
  for (const pattern of SECRET_PATTERNS) {
    out = out.replace(pattern, "[redacted]");
  }
  return out;
}

export function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment: (import.meta.env.MODE as string) || "development",
    // FREE-FIRST（spec §13）：免費層 5,000 events/月，不開 performance
    // tracing／replay，那些會用掉遠更多配額且本票不需要。
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.request) {
        delete event.request.cookies;
        if (event.request.headers) {
          delete event.request.headers["Cookie"];
          delete event.request.headers["cookie"];
        }
        if (event.request.url) {
          event.request.url = event.request.url.split("?")[0];
        }
      }
      if (event.message) {
        event.message = scrubText(event.message);
      }
      if (event.exception?.values) {
        for (const value of event.exception.values) {
          if (value.value) value.value = scrubText(value.value);
        }
      }
      return event;
    },
  });
  return true;
}
