/* The app's slide-out menu: document actions, the recently opened trips and
 * the way into settings. While mounted it publishes window.menu so the
 * backend can refresh the recent list (see UI in src/backpack/ui.py).
 *
 * Properties:
 *   - open: Whether the drawer is showing.
 *   - show_menu: Opens or closes the drawer.
 *
 * State:
 *   - recent: Recently opened trips, newest first, pushed by the backend.
 */
import { useEffect, useState } from "react";
import {
  Button,
  Card,
  CardHeader,
  OverlayDrawer,
  DrawerHeader,
  DrawerHeaderTitle,
  DrawerBody,
  DrawerFooter,
  makeStyles,
  mergeClasses,
  Text,
} from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import api from "./api";
import { icon } from "./icon";
import "./menu.css";

export interface RecentItem {
  title: string;
  meta: string;
  filename: string;
}

const useStyles = makeStyles({
  /* Full-width rows with the icon and label on the left, like menu items. */
  entry: {
    width: "100%",
    justifyContent: "flex-start",
  },
  recent_card: {
    padding: "8px 10px",
    cursor: "pointer",
  },
  footer: {
    display: "block",
  },
});

export function Menu(props: {
  open: boolean;
  show_menu: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const [recent, set_recent] = useState<RecentItem[]>([]);
  const styles = useStyles();

  useEffect(() => {
    window.menu = { set_recent };
    return () => { window.menu = null; };
  }, []);

  const hide_menu = (): void => props.show_menu(false);

  return (
    <OverlayDrawer
      position="start"
      size="small"
      open={props.open}
      onOpenChange={(_event, data) => props.show_menu(data.open)}
    >
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              title={t("menu.close_menu")}
              aria-label={t("menu.close_menu")}
              icon={icon("close")}
              onClick={hide_menu}
            />
          }
        >
          Backpack
        </DrawerHeaderTitle>
      </DrawerHeader>

      <DrawerBody>
        <div className="menu-actions">
          <Button
            className={styles.entry}
            appearance="subtle"
            icon={icon("doc-add")}
            onClick={() => { hide_menu(); api.new_doc(); }}
          >
            {t("menu.new_trip")}
          </Button>
          <Button
            className={styles.entry}
            appearance="subtle"
            icon={icon("folder-open")}
            onClick={() => { hide_menu(); api.open_doc(); }}
          >
            {t("menu.open_trip")}
          </Button>
          <Button
            className={styles.entry}
            appearance="subtle"
            icon={icon("save")}
            onClick={() => { hide_menu(); api.save_doc(); }}
          >
            {t("menu.save")}
          </Button>
          <Button
            className={styles.entry}
            appearance="subtle"
            icon={icon("save-as")}
            onClick={() => { hide_menu(); api.save_doc(null, true); }}
          >
            {t("menu.save_as")}
          </Button>
        </div>

        {recent.length > 0 && (
          <>
            <div className="menu-section">{t("menu.recent")}</div>
            <div className="menu-recent">
              {recent.map((item) => (
                <Card
                  key={item.filename}
                  className={
                    mergeClasses("menu-recent-card", styles.recent_card)}
                  appearance="subtle"
                  onClick={() => { hide_menu(); api.open_doc(item.filename); }}
                >
                  <CardHeader
                    header={{
                      className: "menu-recent-title",
                      children: (
                        <Text weight="semibold" truncate wrap={false}>
                          {item.title.trim() || t("common.untitled_trip")}
                        </Text>
                      )
                    }}
                    description={{
                      className: "menu-recent-meta",
                      children: item.meta
                    }}
                    action={
                      <button
                        type="button"
                        className="icon-btn menu-recent-remove"
                        title={t("menu.remove_recent")}
                        aria-label={t("menu.remove_recent")}
                        onClick={(e) => {
                          e.stopPropagation();
                          void api.remove_recent(item.filename);
                        }}
                      >
                        {icon("close", 14)}
                      </button>
                    }
                  />
                </Card>
              ))}
            </div>
          </>
        )}
      </DrawerBody>

      <DrawerFooter className={styles.footer}>
        <Button
          className={styles.entry}
          appearance="subtle"
          icon={icon("settings")}
          onClick={() => { hide_menu(); api.open_settings(); }}
        >
          {t("menu.settings")}
        </Button>
      </DrawerFooter>
    </OverlayDrawer>
  );
}
