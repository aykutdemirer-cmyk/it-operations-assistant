import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamRulesPanel } from "@/components/PamRulesPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const RULE_ACTIVE = {
  id: "11111111-1111-1111-1111-111111111111",
  user_id: "u1",
  username: "operator1",
  ad_group_id: null,
  ad_group_name: null,
  asset_id: "a1",
  asset_hostname: "srv1.example.local",
  asset_ip_address: "10.0.9.10",
  tag_id: null,
  tag_name: null,
  server_group_id: null,
  server_group_name: null,
  credential_id: "c1",
  credential_name: "srv1-root",
  allow_rdp: true,
  allow_ssh: false,
  allow_web: false,
  is_active: true,
  max_session_duration_mins: 60,
  valid_until: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const RULE_INACTIVE = {
  ...RULE_ACTIVE,
  id: "22222222-2222-2222-2222-222222222222",
  username: "operator2",
  is_active: false,
  allow_rdp: false,
  allow_ssh: true,
  allow_web: true,
};

function mockFetch(handlers: {
  rules?: unknown[];
  tags?: unknown[];
  serverGroups?: unknown[];
  users?: unknown[];
  onRequest?: (method: string, url: string) => unknown;
}) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ADMIN"]) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/pam/rules")) {
        return { ok: true, json: async () => handlers.rules ?? [] };
      }
      if (url.includes("/api/pam/users")) {
        return { ok: true, json: async () => handlers.users ?? [] };
      }
      if (url.includes("/api/settings/ldap/groups")) {
        return { ok: true, json: async () => [] };
      }
      if (url.includes("/api/assets")) {
        return { ok: true, json: async () => [] };
      }
      if (url.includes("/api/pam/vault")) {
        return { ok: true, json: async () => [{ id: "c1", name: "srv1-root" }] };
      }
      if (url.includes("/api/pam/tags")) {
        return { ok: true, json: async () => handlers.tags ?? [] };
      }
      if (url.includes("/api/pam/server-groups")) {
        return { ok: true, json: async () => handlers.serverGroups ?? [] };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );
  return calls;
}

function renderPanel() {
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <AuthProvider>
        <PamRulesPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamRulesPanel", () => {
  it("shows RDP/SSH allow badges and dims inactive rules", async () => {
    mockFetch({ rules: [RULE_ACTIVE, RULE_INACTIVE] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    const row1 = screen.getByText("operator1").closest("tr") as HTMLElement;
    expect(within(row1).getByText(/✅ RDP/)).toBeInTheDocument();
    expect(within(row1).getByText(/❌ SSH/)).toBeInTheDocument();
    expect(within(row1).getByText(/❌ Web/)).toBeInTheDocument();

    const row2Badges = screen.getByText("operator2").closest("tr") as HTMLElement;
    expect(within(row2Badges).getByText(/✅ Web/)).toBeInTheDocument();

    const row2 = screen.getByText("operator2").closest("tr") as HTMLElement;
    expect(row2.className).toContain("ruleInactiveRow");
  });

  it("toggles a rule's active state via the switch", async () => {
    const calls = mockFetch({
      rules: [RULE_ACTIVE],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes(`/api/pam/rules/${RULE_ACTIVE.id}`)) {
          return { ok: true, json: async () => ({ ...RULE_ACTIVE, is_active: false }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    const row = screen.getByText("operator1").closest("tr") as HTMLElement;
    const toggle = within(row).getByRole("checkbox");
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "PUT" && c.url.includes(`/api/pam/rules/${RULE_ACTIVE.id}`)),
      ).toBe(true),
    );
  });

  it("opens the edit modal and saves changes", async () => {
    const calls = mockFetch({
      rules: [RULE_ACTIVE],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes(`/api/pam/rules/${RULE_ACTIVE.id}`)) {
          return { ok: true, json: async () => RULE_ACTIVE };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.editRule }));

    await waitFor(() => expect(screen.getByText(tr.pam.editRuleTitle)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.save }));

    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "PUT" && c.url.includes(`/api/pam/rules/${RULE_ACTIVE.id}`)),
      ).toBe(true),
    );
  });

  it("sends the debounced search text as a backend query parameter", async () => {
    const calls = mockFetch({ rules: [RULE_ACTIVE] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(tr.pam.rulesSearchPlaceholder), { target: { value: "operator1" } });

    await waitFor(
      () => expect(calls.some((c) => c.url.includes("/api/pam/rules") && c.url.includes("search=operator1"))).toBe(true),
      { timeout: 2000 },
    );
  });

  it("creates a tag-targeted rule via the device target type selector", async () => {
    const calls = mockFetch({
      rules: [],
      users: [{ id: "u9", username: "tagged-user", role: "OPERATOR" }],
      tags: [{ id: "t1", name: "Production", created_at: new Date().toISOString() }],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/api/pam/rules")) {
          return { ok: true, json: async () => ({ ...RULE_ACTIVE, id: "new-rule" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    // `load()` yedi paralel isteği (rules/users/adGroups/assets/
    // credentials/tags/serverGroups) TAM olarak bitirmeden forma
    // etkileşim başlarsa `tags` state'i hâlâ boş olabilir — bu yüzden
    // önce boş-liste durumunun (rules=[]) render edildiğini bekliyoruz.
    await waitFor(() => expect(screen.getByText(tr.common.noDataAvailable)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.newRule }));

    fireEvent.change(screen.getByLabelText(tr.pam.columnUser, { exact: true }), { target: { value: "u9" } });
    fireEvent.change(screen.getByLabelText(tr.pam.deviceTargetType, { exact: true }), { target: { value: "tag" } });
    fireEvent.change(screen.getByLabelText(tr.pam.columnTag, { exact: true }), { target: { value: "t1" } });
    fireEvent.change(screen.getByLabelText(tr.pam.columnCredential, { exact: true }), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: tr.pam.create }));

    await waitFor(() => {
      const createCall = calls.find((c) => c.method === "POST" && c.url.includes("/api/pam/rules"));
      expect(createCall).toBeDefined();
    });
  });
});
