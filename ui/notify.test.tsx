import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { NotifyHost } from "./notify";
import { act_bridge, t } from "./test-utils";

function mount_host() {
  render(
    <FluentProvider theme={webLightTheme}>
      <NotifyHost />
    </FluentProvider>,
  );
}

describe("notify", () => {
  it("shows nothing until asked", () => {
    mount_host();
    expect(screen.queryByText("anything")).not.toBeInTheDocument();
  });

  it("shows the message", async () => {
    mount_host();
    void act_bridge(() => window.notify("Route loaded"));
    expect(await screen.findByText("Route loaded")).toBeInTheDocument();
  });

  it("shows an optional title above the message", async () => {
    mount_host();
    void act_bridge(() =>
      window.notify("bad.gpx could not be parsed", "error", "Load failed"),
    );
    expect(await screen.findByText("Load failed")).toBeInTheDocument();
    expect(
      screen.getByText("bad.gpx could not be parsed"),
    ).toBeInTheDocument();
  });

  it("resolves with the chosen action result", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = act_bridge(() =>
      window.notify("No home set", "warning", "", [
        { title: "Settings", result: "settings" },
      ]),
    );
    await user.click(await screen.findByRole("button", { name: "Settings" }));
    await expect(answer).resolves.toBe("settings");
  });

  it("defaults a missing action result to null", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = act_bridge(() =>
      window.notify("Pick one", "info", "", [{ title: "OK" }]),
    );
    await user.click(await screen.findByRole("button", { name: "OK" }));
    await expect(answer).resolves.toBeNull();
  });

  it("resolves null via the dismiss button", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = act_bridge(() => window.notify("Heads up"));
    await user.click(
      await screen.findByRole("button", { name: t("notify.dismiss") }),
    );
    await expect(answer).resolves.toBeNull();
  });

  it("removes the banner once dismissed", async () => {
    mount_host();
    const user = userEvent.setup();
    void act_bridge(() => window.notify("Temporary"));
    await user.click(
      await screen.findByRole("button", { name: t("notify.dismiss") }),
    );
    await waitFor(() =>
      expect(screen.queryByText("Temporary")).not.toBeInTheDocument(),
    );
  });

  it("stacks multiple banners", async () => {
    mount_host();
    act_bridge(() => {
      void window.notify("First");
      void window.notify("Second");
    });
    expect(await screen.findByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("closes only the chosen banner", async () => {
    mount_host();
    const user = userEvent.setup();
    act_bridge(() => {
      void window.notify("Keep me");
      void window.notify("Close me", "info", "", [{ title: "Go", result: 1 }]);
    });
    await user.click(await screen.findByRole("button", { name: "Go" }));
    await waitFor(() =>
      expect(screen.queryByText("Close me")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Keep me")).toBeInTheDocument();
  });

  it("clears every banner and resolves them null", async () => {
    mount_host();
    const [first, second] = act_bridge(
      () => [window.notify("First"), window.notify("Second")] as const,
    );
    expect(await screen.findByText("First")).toBeInTheDocument();
    act_bridge(() => window.clear_notify());
    await waitFor(() => {
      expect(screen.queryByText("First")).not.toBeInTheDocument();
      expect(screen.queryByText("Second")).not.toBeInTheDocument();
    });
    await expect(first).resolves.toBeNull();
    await expect(second).resolves.toBeNull();
  });

  it("is a no-op when there is nothing to clear", () => {
    mount_host();
    act_bridge(() => expect(() => window.clear_notify()).not.toThrow());
  });

  it("throws when the host is not mounted", () => {
    expect(() => window.notify("x")).toThrow("notify host is not mounted");
  });
});
