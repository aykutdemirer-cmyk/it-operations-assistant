import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackendStatus } from "@/components/BackendStatus";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderBackendStatus() {
  return render(
    <LocaleProvider>
      <BackendStatus />
    </LocaleProvider>,
  );
}

describe("BackendStatus", () => {
  it("shows connected when the backend health check succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      }),
    );

    renderBackendStatus();

    await waitFor(() =>
      expect(
        screen.getByText(`Backend: 🟢 ${tr.common.backendConnected}`),
      ).toBeInTheDocument(),
    );
  });

  it("shows disconnected when the backend health check fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network error")),
    );

    renderBackendStatus();

    await waitFor(() =>
      expect(
        screen.getByText(`Backend: 🔴 ${tr.common.backendDisconnected}`),
      ).toBeInTheDocument(),
    );
  });
});
