import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { DialogHost } from "./dialog-host";
import { t } from "./test-utils";

function mount_host() {
  render(
    <FluentProvider theme={webLightTheme}>
      <DialogHost />
    </FluentProvider>,
  );
}

describe("show_dialog", () => {
  it("shows the title and text", async () => {
    mount_host();
    void window.show_dialog("Title", "Body text");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Body text")).toBeInTheDocument();
  });

  it("resolves with the chosen action result", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = window.show_dialog("Save?", "Save changes?", [
      { title: "Yes", result: "yes" },
      { title: "No", result: "no" },
    ]);
    await user.click(await screen.findByRole("button", { name: "Yes" }));
    await expect(answer).resolves.toBe("yes");
  });

  it("defaults a missing result to null", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = window.show_dialog("T", "B", [{ title: "OK" }]);
    await user.click(await screen.findByRole("button", { name: "OK" }));
    await expect(answer).resolves.toBeNull();
  });

  it("resolves null via the close button", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = window.show_dialog("T", "B");
    await user.click(
      await screen.findByRole("button", { name: t("dialog.close") }),
    );
    await expect(answer).resolves.toBeNull();
  });

  it("resolves null on Escape", async () => {
    mount_host();
    const user = userEvent.setup();
    const answer = window.show_dialog("T", "B");
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await expect(answer).resolves.toBeNull();
  });

  it("renders no action buttons for a message-only dialog", async () => {
    mount_host();
    void window.show_dialog("T", "B");
    await screen.findByRole("dialog");
    expect(
      screen.getByRole("button", { name: t("dialog.close") }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("stacks multiple dialogs", async () => {
    mount_host();
    void window.show_dialog("First", "one");
    void window.show_dialog("Second", "two");
    expect(await screen.findByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("closes the dialog once an action is chosen", async () => {
    const user = userEvent.setup();
    mount_host();
    const answer = window.show_dialog("Bye", "closing", [
      { title: "OK", result: 1 },
    ]);
    await user.click(await screen.findByRole("button", { name: "OK" }));
    await expect(answer).resolves.toBe(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("throws when the host is not mounted", () => {
    expect(() => window.show_dialog("T", "B")).toThrow(
      "dialog host is not mounted",
    );
  });
});
