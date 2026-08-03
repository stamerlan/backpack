import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { Busy } from "./busy";

function mount_busy() {
  render(
    <FluentProvider theme={webLightTheme}>
      <Busy />
    </FluentProvider>,
  );
}

describe("set_busy", () => {
  it("hides the overlay until asked", () => {
    mount_busy();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows the overlay with a label", async () => {
    mount_busy();
    window.set_busy(true, "Loading routes...");
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("Loading routes...")).toBeInTheDocument();
  });

  it("clears the overlay", async () => {
    mount_busy();
    window.set_busy(true, "Loading routes...");
    await screen.findByRole("progressbar");
    window.set_busy(false);
    await waitFor(() =>
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument(),
    );
  });

  it("no-ops when the host is not mounted", () => {
    expect(() => window.set_busy(true, "x")).not.toThrow();
  });
});
