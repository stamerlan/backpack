/* The document's lead card, carrying the trip title and its notes. Edits are
 * reported upwards on every keystroke and sent to the backend on blur.
 *
 * Properties:
 *   - id: Model id of the trip card, quoted back on every commit.
 *   - title: Trip title, owned by the document view.
 *   - notes: Trip notes as markdown, owned by the document view.
 *   - on_change: Reports the edited title and notes on every keystroke.
 */
import { Card, Input } from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import api from "./api";
import { MdInput } from "./md-input";
import "./trip-card.css";

export function TripCard(props: {
  id: string;
  title: string;
  notes: string;
  on_change: (title: string, notes: string) => void;
}) {
  const { t } = useTranslation();
  const commit = (): void => {
    void api.set_trip_info(props.id, props.title, props.notes);
  };

  return (
    <Card className="trip-card">
      <Input
        className="trip-card-title"
        appearance="underline"
        placeholder={t("common.untitled_trip")}
        value={props.title}
        onChange={(_event, data) => props.on_change(data.value, props.notes)}
        onBlur={commit}
      />
      <MdInput
        placeholder={t("trip_card.notes_placeholder")}
        value={props.notes}
        min_height={160}
        on_change={(value) => props.on_change(props.title, value)}
        on_commit={commit}
      />
    </Card>
  );
}
