/* The document's lead card, carrying the trip title and its notes. Edits are
 * reported upwards on every keystroke and sent to the backend on blur.
 *
 * Properties:
 *   - id: Model id of the trip card, quoted back on every commit.
 *   - title: Trip title, owned by the document view.
 *   - notes: Trip notes as markdown, owned by the document view.
 *   - on_change: Reports the edited title and notes on every keystroke.
 */
import {
  Card,
  Input,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import api from "./api";
import { MdInput } from "./md-input";

/* Styling Fluent components through makeStyles keeps the overrides in Griffel's
 * atomic layer, so they win over the component's own styles without leaning on
 * the internal fui-* class names for specificity.
 */
const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "16px",
  },
  title: {
    border: "none",
    borderRadius: tokens.borderRadiusSmall,
    paddingLeft: 0,
    paddingRight: 0,
    backgroundColor: "transparent",
    boxShadow: "inset 0 -1px 0 transparent",
    "::before": { display: "none" },
    "::after": { display: "none" },
    ":hover": {
      backgroundColor: `color-mix(in srgb, ${
        tokens.colorNeutralForeground1
      } 4%, transparent)`,
    },
    ":focus-within": {
      boxShadow: `inset 0 -1px 0 ${tokens.colorNeutralForeground1}`,
    },
  },
  titleInput: {
    paddingLeft: 0,
    paddingRight: 0,
    fontFamily: tokens.fontFamilyBase,
    fontSize: tokens.fontSizeHero800,
    lineHeight: tokens.lineHeightHero800,
    fontWeight: tokens.fontWeightSemibold,
  },
});

export function TripCard(props: {
  id: string;
  title: string;
  notes: string;
  on_change: (title: string, notes: string) => void;
}) {
  const { t } = useTranslation();
  const styles = useStyles();
  const commit = (): void => {
    void api.set_trip_info(props.id, props.title, props.notes);
  };

  return (
    <Card className={styles.card}>
      <Input
        className={styles.title}
        input={{ className: styles.titleInput }}
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
