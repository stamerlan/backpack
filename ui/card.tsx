/* One card the assistant put in the turn log: an error, a plain message, a
 * suggestion or a request for input. The kind picks the message bar's colour
 * and nothing else, so a new kind only needs a row in card_intent.
 *
 * Properties:
 *   - card: The card as the backend sent it: kind, title, text and the
 *     actions to offer.
 *   - on_action: Reports the id of the action the user chose, which is all
 *     the card knows about what it does.
 */
import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  MessageBarTitle,
  type MessageBarIntent,
} from "@fluentui/react-components";
import "./card.css";

export interface ChatCardAction {
  id: string;
  label: string;
  appearance: "primary" | "secondary" | "subtle";
}

export interface ChatCardData {
  card_kind: "error" | "message" | "suggest" | "input";
  title: string;
  text: string;
  actions: ChatCardAction[];
}

const card_intent: Record<ChatCardData["card_kind"], MessageBarIntent> = {
  error: "error",
  message: "info",
  suggest: "warning",
  input: "info",
};

export function ChatCardView(props: {
  card: ChatCardData;
  on_action?: (action_id: string) => void;
}) {
  const { card, on_action } = props;

  return (
    <MessageBar intent={card_intent[card.card_kind]} layout="multiline">
      <MessageBarBody>
        {card.title && <MessageBarTitle>{card.title}</MessageBarTitle>}
        <span className="chat-card-text">{card.text}</span>
      </MessageBarBody>
      {card.actions.length > 0 && (
        <MessageBarActions>
          {card.actions.map((a) => (
            <Button
              key={a.id}
              size="small"
              appearance={a.appearance}
              onClick={() => on_action?.(a.id)}
            >
              {a.label}
            </Button>
          ))}
        </MessageBarActions>
      )}
    </MessageBar>
  );
}
