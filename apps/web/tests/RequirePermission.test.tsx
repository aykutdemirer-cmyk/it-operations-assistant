/**
 * Gerçek bir üretim hatasının regresyon testi: `router.replace(...)`
 * önceden render GÖVDESİNDE doğrudan çağrılıyordu ("Cannot update a
 * component (Router) while rendering a different component" — bu proje
 * `LoginForm.tsx`'te AYNI hatayı daha önce de bulup düzeltmişti).
 * Yönlendirme artık bir `useEffect` içinde.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

import { RequirePermission } from "@/components/RequirePermission";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  replaceMock.mockClear();
});

function renderGuarded(permission: "DASHBOARD_VIEW" = "DASHBOARD_VIEW") {
  return render(
    <LocaleProvider>
      <AuthProvider>
        <RequirePermission permission={permission}>
          <p>korunan içerik</p>
        </RequirePermission>
      </AuthProvider>
    </LocaleProvider>,
  );
}

function mockAuthMe(user: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/auth/me")) {
        return Promise.resolve({ ok: true, json: async () => user });
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    }),
  );
}

describe("RequirePermission", () => {
  it("does not call router.replace synchronously during the initial render (no token)", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    renderGuarded();

    // Render SIRASINDA hiç çağrılmamalı — yalnızca `useEffect` (mount
    // sonrası) tetiklenir. React'in "Cannot update a component while
    // rendering a different component" uyarısı da hiç LOGLANMAMALI.
    expect(replaceMock).not.toHaveBeenCalled();
    const reactPurityWarning = consoleError.mock.calls.some((args) =>
      String(args[0]).includes("while rendering a different component"),
    );
    expect(reactPurityWarning).toBe(false);
  });

  it("redirects to /login after mount when there is no logged-in user", async () => {
    renderGuarded();

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith(expect.stringContaining("/login?next=")));
  });

  it("shows a 403 without redirecting when the user lacks the permission", async () => {
    setLoggedInToken();
    mockAuthMe(mockCurrentUser(["PAM_ACCESS"]));

    renderGuarded("DASHBOARD_VIEW");

    await waitFor(() => expect(screen.getByText("403")).toBeInTheDocument());
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("renders children when the user has the required permission", async () => {
    setLoggedInToken();
    mockAuthMe(mockCurrentUser(["DASHBOARD_VIEW"]));

    renderGuarded("DASHBOARD_VIEW");

    await waitFor(() => expect(screen.getByText("korunan içerik")).toBeInTheDocument());
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("shows the loading label before auth resolves, not the sign-in prompt", () => {
    setLoggedInToken();
    mockAuthMe(mockCurrentUser(["DASHBOARD_VIEW"]));

    renderGuarded("DASHBOARD_VIEW");

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });
});
