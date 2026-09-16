import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionKeystrokesModal } from "@/components/SessionKeystrokesModal";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function mockFetch(keystrokes: { id: string; recorded_at: string; data: string }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ADMIN"]) };
      }
      if (url.includes("/keystrokes")) {
        return { ok: true, json: async () => keystrokes };
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    }),
  );
}

function renderModal(sessionId = "s1") {
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <AuthProvider>
        <SessionKeystrokesModal sessionId={sessionId} onClose={() => {}} />
      </AuthProvider>
    </LocaleProvider>,
  );
}

function chunk(data: string, id: string, at: string) {
  return { id, recorded_at: at, data };
}

describe("SessionKeystrokesModal", () => {
  it("shows an empty-state message when no keystrokes were recorded", async () => {
    mockFetch([]);
    renderModal();

    await waitFor(() => expect(screen.getByText(tr.pam.keystrokesEmpty)).toBeInTheDocument());
  });

  it("groups raw per-character keystroke chunks into a command line on Enter", async () => {
    const at = "2026-01-01T10:14:02.000Z";
    mockFetch([
      chunk("l", "1", at),
      chunk("s", "2", at),
      chunk(" ", "3", at),
      chunk("-", "4", at),
      chunk("l", "5", at),
      chunk("\r", "6", at),
    ]);
    renderModal();

    await waitFor(() => expect(screen.getByText(/ls -l/)).toBeInTheDocument());
  });

  it("applies backspace by removing the previous character", async () => {
    const at = "2026-01-01T10:14:02.000Z";
    mockFetch([
      chunk("p", "1", at),
      chunk("w", "2", at),
      chunk("d", "3", at),
      chunk("x", "4", at),
      chunk("\b", "5", at), // typo correction: "pwdx" -> "pwd"
      chunk("\r", "6", at),
    ]);
    renderModal();

    await waitFor(() => expect(screen.getByText(/pwd(?!x)/)).toBeInTheDocument());
    expect(screen.queryByText(/pwdx/)).not.toBeInTheDocument();
  });
});
