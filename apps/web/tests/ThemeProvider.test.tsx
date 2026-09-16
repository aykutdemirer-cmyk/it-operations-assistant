import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider, useTheme } from "@/lib/theme/ThemeProvider";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={() => setTheme("cyber-neon")}>Neon</button>
      <button onClick={() => setTheme("enterprise-light")}>Light</button>
      <button onClick={() => setTheme("fortios-dark")}>Dark</button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  window.localStorage.clear();
});

describe("ThemeProvider", () => {
  it("defaults to fortios-dark", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("theme")).toHaveTextContent("fortios-dark");
  });

  it("sets data-theme=fortios-dark on the html element after mount", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(document.documentElement.dataset.theme).toBe("fortios-dark");
  });

  it("switches to a chosen theme and updates the DOM attribute", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Neon"));
    });

    expect(screen.getByTestId("theme")).toHaveTextContent("cyber-neon");
    expect(document.documentElement.dataset.theme).toBe("cyber-neon");
  });

  it("persists the chosen theme to localStorage", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Light"));
    });

    expect(window.localStorage.getItem("itops-theme")).toBe("enterprise-light");
  });

  it("restores a persisted theme on mount", async () => {
    window.localStorage.setItem("itops-theme", "midnight-blue");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("theme")).toHaveTextContent("midnight-blue");
    expect(document.documentElement.dataset.theme).toBe("midnight-blue");
  });

  it("migrates the legacy 'dark' value to fortios-dark", async () => {
    window.localStorage.setItem("itops-theme", "dark");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("theme")).toHaveTextContent("fortios-dark");
    expect(document.documentElement.dataset.theme).toBe("fortios-dark");
    expect(window.localStorage.getItem("itops-theme")).toBe("fortios-dark");
  });

  it("migrates the legacy 'light' value to enterprise-light", async () => {
    window.localStorage.setItem("itops-theme", "light");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("theme")).toHaveTextContent("enterprise-light");
    expect(window.localStorage.getItem("itops-theme")).toBe("enterprise-light");
  });

  it("throws when useTheme is used outside a ThemeProvider", () => {
    function Bare() {
      useTheme();
      return null;
    }
    expect(() => render(<Bare />)).toThrow("useTheme must be used within a ThemeProvider");
  });
});
