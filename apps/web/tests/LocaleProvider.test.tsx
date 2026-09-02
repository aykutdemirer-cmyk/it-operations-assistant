import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LocaleProvider, useLocale } from "@/lib/i18n/LocaleProvider";

function Probe() {
  const { locale, setLocale, t } = useLocale();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="label">{t.nav.dashboard}</span>
      <button onClick={() => setLocale("en")}>Switch to EN</button>
      <button onClick={() => setLocale("tr")}>Switch to TR</button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.lang = "";
});

afterEach(() => {
  window.localStorage.clear();
});

describe("LocaleProvider", () => {
  it("defaults to Turkish", () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    expect(screen.getByTestId("locale")).toHaveTextContent("tr");
    expect(screen.getByTestId("label")).toHaveTextContent("Dashboard");
  });

  it("switches to English and updates translated text", () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Switch to EN"));
    });

    expect(screen.getByTestId("locale")).toHaveTextContent("en");
  });

  it("persists the chosen locale to localStorage", () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Switch to EN"));
    });

    expect(window.localStorage.getItem("itops-locale")).toBe("en");
  });

  it("restores a persisted locale on mount", async () => {
    window.localStorage.setItem("itops-locale", "en");

    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    expect(await screen.findByTestId("locale")).toHaveTextContent("en");
  });

  it("updates document.documentElement.lang when the locale changes", () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    act(() => {
      fireEvent.click(screen.getByText("Switch to EN"));
    });

    expect(document.documentElement.lang).toBe("en");
  });

  it("throws when useLocale is used outside a LocaleProvider", () => {
    function Bare() {
      useLocale();
      return null;
    }
    expect(() => render(<Bare />)).toThrow(
      "useLocale must be used within a LocaleProvider",
    );
  });
});
