import { beforeEach, describe, expect, it, vi } from "vitest";

const initMock = vi.fn();

vi.mock("@sentry/browser", () => ({
  init: (...args: unknown[]) => initMock(...args),
}));

import { initSentry } from "./observability";

describe("initSentry", () => {
  beforeEach(() => {
    initMock.mockClear();
    vi.unstubAllEnvs();
  });

  it("is a no-op without VITE_SENTRY_DSN", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");

    const result = initSentry();

    expect(result).toBe(false);
    expect(initMock).not.toHaveBeenCalled();
  });

  it("initializes Sentry when VITE_SENTRY_DSN is set", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://example@sentry.io/1");

    const result = initSentry();

    expect(result).toBe(true);
    expect(initMock).toHaveBeenCalledTimes(1);
    const config = initMock.mock.calls[0][0];
    expect(config.dsn).toBe("https://example@sentry.io/1");
    // FREE-FIRST：不開 performance tracing，免得吃掉免費層配額。
    expect(config.tracesSampleRate).toBe(0);
    expect(config.sendDefaultPii).toBe(false);
  });

  it("scrubs cookie headers and query strings before sending", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://example@sentry.io/1");
    initSentry();
    const { beforeSend } = initMock.mock.calls[0][0];

    const event = beforeSend({
      request: {
        url: "https://option-chaser.vercel.app/api/scenarios?owner=abc",
        headers: { Cookie: "oc_owner=secret-token" },
        cookies: { oc_owner: "secret-token" },
      },
    });

    expect(event.request.url).toBe(
      "https://option-chaser.vercel.app/api/scenarios",
    );
    expect(event.request.headers.Cookie).toBeUndefined();
    expect(event.request.cookies).toBeUndefined();
  });

  it("masks bearer tokens and connection strings in messages", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://example@sentry.io/1");
    initSentry();
    const { beforeSend } = initMock.mock.calls[0][0];

    const event = beforeSend({
      message: "auth failed with Bearer abc123XYZ against postgres://u:p@h/db",
    });

    expect(event.message).not.toContain("abc123XYZ");
    expect(event.message).not.toContain("postgres://u:p@h/db");
    expect(event.message).toContain("[redacted]");
  });
});
