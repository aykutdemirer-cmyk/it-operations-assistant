import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  window.localStorage.clear();
});

function renderSwitcher() {
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <ThemeSwitcher />
      </ThemeProvider>
    </LocaleProvider>,
  );
}

describe("ThemeSwitcher", () => {
  it("lists all four themes and defaults to fortios-dark", () => {
    renderSwitcher();
    const select = screen.getByLabelText(tr.settings.theme) as HTMLSelectElement;
    expect(select.value).toBe("fortios-dark");
    expect(screen.getByRole("option", { name: tr.settings.themeCyberNeon })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: tr.settings.themeMidnightBlue })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: tr.settings.themeEnterpriseLight })).toBeInTheDocument();
  });

  it("applies the chosen theme to the html element and localStorage", () => {
    renderSwitcher();
    fireEvent.change(screen.getByLabelText(tr.settings.theme), { target: { value: "midnight-blue" } });

    expect(document.documentElement.dataset.theme).toBe("midnight-blue");
    expect(window.localStorage.getItem("itops-theme")).toBe("midnight-blue");
  });
});
