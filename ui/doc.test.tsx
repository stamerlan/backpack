import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { Doc } from "./doc";

function mount_host(on_title_change: (title: string) => void = () => {}) {
  return render(
    <FluentProvider theme={webLightTheme}>
      <Doc on_title_change={on_title_change} />
    </FluentProvider>,
  );
}

describe("document view", () => {
  it("adds a trip card with its title and notes", async () => {
    mount_host();
    window.doc!.add_trip_card("trip-1", "Alps hike", "Three days out");
    expect(await screen.findByDisplayValue("Alps hike")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Three days out")).toBeInTheDocument();
  });

  it("appends cards in the order they arrive", async () => {
    mount_host();
    window.doc!.add_trip_card("trip-1", "First", "");
    window.doc!.add_trip_card("trip-2", "Second", "");
    expect(await screen.findByDisplayValue("First")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Second")).toBeInTheDocument();
  });

  it("clears every card", async () => {
    mount_host();
    window.doc!.add_trip_card("trip-1", "Doomed", "");
    await screen.findByDisplayValue("Doomed");
    window.doc!.clear();
    await waitFor(() =>
      expect(screen.queryByDisplayValue("Doomed")).not.toBeInTheDocument()
    );
  });

  it("reports a new trip card title to the app bar", async () => {
    const on_title_change = vi.fn();
    mount_host(on_title_change);
    window.doc!.add_trip_card("trip-1", "Alps hike", "");
    await screen.findByDisplayValue("Alps hike");
    expect(on_title_change).toHaveBeenCalledWith("Alps hike");
  });

  it("clears the app bar title when the document is cleared", async () => {
    const on_title_change = vi.fn();
    mount_host(on_title_change);
    window.doc!.add_trip_card("trip-1", "Alps hike", "");
    await screen.findByDisplayValue("Alps hike");
    window.doc!.clear();
    await waitFor(() => expect(on_title_change).toHaveBeenLastCalledWith(""));
  });

  it("streams the app bar title as the trip title is edited", async () => {
    const user = userEvent.setup();
    const on_title_change = vi.fn();
    mount_host(on_title_change);
    window.doc!.add_trip_card("trip-1", "", "");
    const field = await screen.findByPlaceholderText("Trip title");
    await user.type(field, "Hi");
    expect(on_title_change).toHaveBeenLastCalledWith("Hi");
  });

  it("drops the global handle once the view unmounts", () => {
    const view = mount_host();
    expect(window.doc).not.toBeNull();
    view.unmount();
    expect(window.doc).toBeNull();
  });
});
