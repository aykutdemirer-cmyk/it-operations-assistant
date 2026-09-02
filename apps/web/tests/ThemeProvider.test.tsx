import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider, useTheme } from "@/lib/theme/ThemeProvider";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={() => setTheme("light")}>Light</button>
      <button onClick={() => setTheme("dark")}>Dark</button>
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
  it("defaults to dark", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
  });

  it("sets data-theme=dark on the html element after mount", async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("switches to light and updates the DOM attribute", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Light"));
    });

    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(document.documentElement.dataset.theme).toBe("light");
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

    expect(window.localStorage.getItem("itops-theme")).toBe("light");
  });

  it("restores a persisted theme on mount", async () => {
    window.localStorage.setItem("itops-theme", "light");

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("theme")).toHaveTextContent("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("throws when useTheme is used outside a ThemeProvider", () => {
    function Bare() {
      useTheme();
      return null;
    }
    expect(() => render(<Bare />)).toThrow("useTheme must be used within a ThemeProvider");
  });
});
