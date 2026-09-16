import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TicketsPanel } from "@/components/TicketsPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

const k = tr.tickets;

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const CATEGORIES = [
  { id: "cat-net", name: "Ağ", is_active: true },
  { id: "cat-srv", name: "Sunucu", is_active: true },
];
const DEPARTMENTS = [{ id: "dep-it", name: "IT", is_active: true }];

const TICKET = {
  id: "t1",
  ticket_number: "INC-2026-0001",
  title: "Switch portu down",
  description: "port 12 flapping",
  category_id: "cat-net",
  category_name: "Ağ",
  department_id: "dep-it",
  department_name: "IT",
  priority: "HIGH",
  status: "OPEN",
  created_by: "u1",
  created_by_username: "operator1",
  assigned_to: null,
  assigned_to_username: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  resolved_at: null,
  sla_due_at: new Date(Date.now() + 3600_000).toISOString(),
  comments: [
    {
      id: "c0",
      ticket_id: "t1",
      author_id: "u1",
      author_username: "operator1",
      event: "created",
      body: null,
      status_from: null,
      status_to: "OPEN",
      assigned_from_username: null,
      assigned_to_username: null,
      created_at: new Date().toISOString(),
    },
  ],
};

const LIST_BODY = {
  tickets: [TICKET],
  total: 1,
  stats: { open_tickets: 3, assigned_to_me: 1, critical_or_overdue: 2, resolved_this_month: 5 },
};

function mockFetch(handlers: {
  role?: "ADMIN" | "OPERATOR";
  list?: unknown;
  onRequest?: (method: string, url: string, body?: string) => unknown;
}) {
  const calls: { method: string; url: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body as string | undefined;
      calls.push({ method, url, body });

      if (url.includes("/api/auth/me")) {
        return {
          ok: true,
          json: async () => mockCurrentUser(["TICKETS_VIEW"], { role: handlers.role ?? "OPERATOR" }),
        };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/tickets/categories")) {
        return { ok: true, json: async () => CATEGORIES };
      }
      if (url.includes("/api/tickets/departments")) {
        return { ok: true, json: async () => DEPARTMENTS };
      }
      if (url.includes("/api/tickets/assignable-users")) {
        return { ok: true, json: async () => [] };
      }
      if (url.includes("/api/tickets/sla-policy")) {
        return { ok: true, json: async () => ({ CRITICAL: 4, HIGH: 24, MEDIUM: 72, LOW: 168 }) };
      }
      if (url.includes("/api/tickets/export.csv")) {
        return { ok: true, blob: async () => new Blob(["ticket_number\n"], { type: "text/csv" }) };
      }
      if (url.includes("/api/tickets/metrics")) {
        return {
          ok: true,
          json: async () => ({
            total: 5,
            open_tickets: 3,
            closed_tickets: 2,
            overdue_open: 1,
            avg_resolution_hours: 12.5,
            sla_compliance_pct: 80,
            by_status: { OPEN: 3, RESOLVED: 2 },
            by_priority: { HIGH: 4, LOW: 1 },
            by_category: { Ağ: 5 },
            by_department: { IT: 5 },
            daily: [{ day: "2026-09-01", created: 1, resolved: 0 }],
          }),
        };
      }
      if (/\/api\/tickets\/[^/?]+/.test(url)) {
        return { ok: true, json: async () => TICKET };
      }
      if (url.includes("/api/tickets")) {
        return { ok: true, json: async () => handlers.list ?? LIST_BODY };
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
      <ThemeProvider>
        <AuthProvider>
          <TicketsPanel />
        </AuthProvider>
      </ThemeProvider>
    </LocaleProvider>,
  );
}

describe("TicketsPanel", () => {
  it("renders KPI cards and the ticket table with department + category columns", async () => {
    mockFetch({});
    renderPanel();

    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());
    const openCard = screen.getByText(k.kpiOpen).closest('[class*="kpiCard"]')!;
    expect(openCard).toHaveTextContent("3");
    const row = screen.getByText("Switch portu down").closest("tr")!;
    expect(within(row).getByText("IT")).toBeInTheDocument(); // Departman
    expect(within(row).getByText("Ağ")).toBeInTheDocument(); // Kategori
  });

  it("passes the selected category_id to the API", async () => {
    const calls = mockFetch({});
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.change(screen.getByDisplayValue(`${k.filterCategory}: ${k.all}`), { target: { value: "cat-srv" } });

    await waitFor(() =>
      expect(calls.some((c) => c.method === "GET" && c.url.includes("category_id=cat-srv"))).toBe(true),
    );
  });

  it("shows the Ticket Settings button only for ADMIN", async () => {
    mockFetch({ role: "OPERATOR" });
    const { unmount } = renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: k.settingsButton })).not.toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    mockFetch({ role: "ADMIN" });
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: k.settingsButton })).toBeInTheDocument();
  });

  it("creates a ticket with a dynamic category and posts to the API", async () => {
    const calls = mockFetch({
      onRequest: (method, url, body) => {
        if (method === "POST" && url.endsWith("/api/tickets")) {
          return { ok: true, status: 201, json: async () => ({ ...TICKET, id: "t2", title: JSON.parse(body!).title }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: k.new }));
    const dialog = await screen.findByRole("dialog", { name: k.createTitle });
    fireEvent.change(within(dialog).getByLabelText(k.fieldTitle), { target: { value: "Yeni sorun" } });
    fireEvent.click(within(dialog).getByRole("button", { name: k.create }));

    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/api/tickets"));
      expect(post).toBeTruthy();
      expect(JSON.parse(post!.body!).category_id).toBe("cat-net");
    });
  });

  it("admin opens Ticket Settings and adds a department", async () => {
    const calls = mockFetch({
      role: "ADMIN",
      onRequest: (method, url) => {
        if (method === "POST" && url.endsWith("/api/tickets/departments")) {
          return { ok: true, status: 201, json: async () => ({ id: "dep-new", name: "Depo", is_active: true }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: k.settingsButton }));
    const dialog = await screen.findByRole("dialog", { name: k.settingsTitle });
    fireEvent.change(within(dialog).getByPlaceholderText(k.newDepartmentPlaceholder), { target: { value: "Depo" } });
    fireEvent.click(within(dialog).getByRole("button", { name: k.add }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/api/tickets/departments"))).toBe(true),
    );
  });

  it("passes overdue=true when the overdue filter is checked (Faz 67)", async () => {
    const calls = mockFetch({});
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(k.filterOverdue));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "GET" && c.url.includes("overdue=true"))).toBe(true),
    );
  });

  it("passes mine=true when the assigned-to-me filter is checked (Faz 69)", async () => {
    const calls = mockFetch({ role: "ADMIN" });
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(k.filterMine));

    await waitFor(() => expect(calls.some((c) => c.method === "GET" && c.url.includes("mine=true"))).toBe(true));
  });

  it("requests the CSV export with current filters (Faz 69)", async () => {
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    try {
      const calls = mockFetch({});
      renderPanel();
      await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

      fireEvent.click(screen.getByRole("button", { name: k.exportCsv }));

      await waitFor(() => expect(calls.some((c) => c.url.includes("/api/tickets/export.csv"))).toBe(true));
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });

  it("toggles the Reports panel and loads ticket metrics (Faz 68)", async () => {
    const calls = mockFetch({});
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: k.reportsToggle }));

    await waitFor(() => expect(calls.some((c) => c.url.includes("/api/tickets/metrics"))).toBe(true));
    await waitFor(() => expect(screen.getByText(k.metrics.title)).toBeInTheDocument());
    expect(screen.getByText(k.metrics.slaCompliance)).toBeInTheDocument();
  });

  it("admin edits an SLA hour value in the SLA tab (Faz 67)", async () => {
    const calls = mockFetch({
      role: "ADMIN",
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes("/api/tickets/sla-policy/")) {
          return { ok: true, json: async () => ({ CRITICAL: 2, HIGH: 24, MEDIUM: 72, LOW: 168 }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("INC-2026-0001")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: k.settingsButton }));
    const dialog = await screen.findByRole("dialog", { name: k.settingsTitle });
    fireEvent.click(within(dialog).getByRole("tab", { name: k.tabSla }));

    const input = await within(dialog).findByLabelText(`${k.priorityCRITICAL} — ${k.slaHoursLabel}`);
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.click(within(dialog).getAllByRole("button", { name: k.add })[0]);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT" && c.url.includes("/api/tickets/sla-policy/CRITICAL"))).toBe(true),
    );
  });
});
