import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { Splash } from "./splash";
import { act_bridge } from "./test-utils";

function mount_splash(): HTMLElement {
  const { container } = render(
    <FluentProvider theme={webLightTheme}>
      <Splash />
    </FluentProvider>,
  );
  const splash = container.querySelector<HTMLElement>(".splash");
  if (splash === null)
    throw new Error("splash is not rendered");
  return splash;
}

describe("set_ready", () => {
  it("covers the window until the backend is ready", () => {
    const splash = mount_splash();
    expect(splash).not.toHaveClass("ready");
    expect(splash).toHaveAttribute("aria-busy", "true");
  });

  it("lowers the cover", () => {
    const splash = mount_splash();
    act_bridge(() => window.set_ready());
    expect(splash).toHaveClass("ready");
    expect(splash).toHaveAttribute("aria-busy", "false");
  });

  it("no-ops when the host is not mounted", () => {
    expect(() => window.set_ready()).not.toThrow();
  });
});
