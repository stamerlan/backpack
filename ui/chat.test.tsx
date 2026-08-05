import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { Chat, type Turn } from "./chat";
import type { ChatCardData } from "./card";

/* Chat is now presentational: it renders the turns handed to it and calls a
 * card item's resolve when an action is clicked. The turn state and the
 * add_card promise wiring live in AssistView, so tests drive Chat through
 * props directly.
 */
function render_chat(turns: Turn[]) {
  render(
    <FluentProvider theme={webLightTheme}>
      <Chat
        chat_id="c1"
        visible={true}
        turns={turns}
        busy={false}
        models={[]}
        selected_model=""
        on_model_change={() => {}}
      />
    </FluentProvider>,
  );
}

const error_card: ChatCardData = {
  card_kind: "error",
  title: "",
  text: "The model is overloaded",
  actions: [{ id: "retry", label: "Retry", appearance: "primary" }],
};

describe("chat error card", () => {
  it("shows the card text and its actions", async () => {
    render_chat([
      {
        id: "t1",
        prompt: "Plan my trip",
        items: [{ kind: "card", data: error_card, resolve: () => {} }],
      },
    ]);
    expect(await screen.findByText("The model is overloaded"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("calls resolve with the clicked action id", async () => {
    const resolve = vi.fn();
    const user = userEvent.setup();
    render_chat([
      {
        id: "t1",
        prompt: "Plan my trip",
        items: [{ kind: "card", data: error_card, resolve }],
      },
    ]);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(resolve).toHaveBeenCalledWith("retry");
  });
});
