import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "../../src/ui/api";
import { Assist } from "../../src/ui/assist";
import { DialogHost } from "../../src/ui/dialog-host";
import { act_bridge, render_ui, t } from "./test-utils";

vi.mock("../../src/ui/api", () => ({
  default: { del_chat: vi.fn() },
}));

function mount_host() {
  return render_ui(
    <>
      <Assist open />
      <DialogHost />
    </>,
  );
}

/* Open the chat picker and click the delete button of its only chat. */
async function click_delete(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: t("assist.chats") }));
  await user.click(await screen.findByLabelText(t("assist.delete_chat")));
}

describe("assistant chat deletion", () => {
  afterEach(() => vi.mocked(api.del_chat).mockClear());

  it("deletes an empty chat without asking", async () => {
    const user = userEvent.setup();
    mount_host();
    act_bridge(() => window.assist!.new_chat("chat-1", "Empty"));
    await click_delete(user);
    expect(api.del_chat).toHaveBeenCalledWith("chat-1");
    expect(
      screen.queryByText(t("assist.delete_confirm_title"))
    ).not.toBeInTheDocument();
  });

  it("deletes a chat with turns once the user confirms", async () => {
    const user = userEvent.setup();
    mount_host();
    act_bridge(() => {
      window.assist!.new_chat("chat-1", "Plans");
      window.assist!.new_turn("chat-1", "turn-1", "Hello");
      window.assist!.end_turn("chat-1");
    });
    await click_delete(user);
    expect(
      await screen.findByText(t("assist.delete_confirm_title"))
    ).toBeInTheDocument();
    expect(api.del_chat).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: t("dialog.delete") }));
    await waitFor(() => expect(api.del_chat).toHaveBeenCalledWith("chat-1"));
  });

  it("keeps a chat with turns when the delete is cancelled", async () => {
    const user = userEvent.setup();
    mount_host();
    act_bridge(() => {
      window.assist!.new_chat("chat-1", "Plans");
      window.assist!.new_turn("chat-1", "turn-1", "Hello");
      window.assist!.end_turn("chat-1");
    });
    await click_delete(user);
    await user.click(
      await screen.findByRole("button", { name: t("dialog.cancel") })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: t("dialog.cancel") })
      ).not.toBeInTheDocument()
    );
    expect(api.del_chat).not.toHaveBeenCalled();
  });
});
