import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  makeStyles,
  tokens,
  Button,
  Card,
  CardHeader,
  OverlayDrawer,
  DrawerHeader,
  DrawerHeaderTitle,
  DrawerBody,
  DrawerFooter,
  Text,
} from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";

const use_styles = makeStyles({
  actions: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    paddingBottom: "8px",
  },
  action_btn: {
    width: "100%",
    justifyContent: "flex-start",
  },
  section_label: {
    padding: "4px 0",
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground3,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  recent: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  recent_card: {
    padding: "8px 10px",
    cursor: "pointer",
  },
  recent_meta: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3,
  },
  footer: {
    display: "block",
  },
  footer_btn: {
    width: "100%",
    justifyContent: "flex-start",
  },
});

export interface RecentItem {
  title: string;
  meta: string;
  filename: string;
}

class MenuView {
  #recent: RecentItem[];
  #set_recent: Dispatch<SetStateAction<RecentItem[]>>;

  constructor() {
    [this.#recent, this.#set_recent] = useState<RecentItem[]>([]);
  }

  get recent(): RecentItem[] {
    return this.#recent;
  }

  set_recent(items: RecentItem[]): void {
    this.#set_recent(items);
  }
}

export function Menu(props: {
  open: boolean;
  show_menu: (open: boolean) => void;
}) {
  const styles = use_styles();
  const menu = new MenuView();

  useEffect(() => {
    window.menu = menu;
    return () => { window.menu = null; };
  });

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
              title="Close menu"
              aria-label="Close menu"
              icon={icon("close")}
              onClick={hide_menu}
            />
          }
        >
          Backpack
        </DrawerHeaderTitle>
      </DrawerHeader>

      <DrawerBody>
        <div className={styles.actions}>
          <Button
            className={styles.action_btn}
            appearance="subtle"
            icon={icon("doc-add")}
            onClick={() => { hide_menu(); api.new_doc(); }}
          >
            New trip
          </Button>
          <Button
            className={styles.action_btn}
            appearance="subtle"
            icon={icon("folder-open")}
            onClick={() => { hide_menu(); api.open_doc(); }}
          >
            Open trip...
          </Button>
          <Button
            className={styles.action_btn}
            appearance="subtle"
            icon={icon("save")}
            onClick={() => { hide_menu(); api.save_doc(); }}
          >
            Save
          </Button>
          <Button
            className={styles.action_btn}
            appearance="subtle"
            icon={icon("save-as")}
            onClick={() => { hide_menu(); api.save_doc(null, true); }}
          >
            Save as...
          </Button>
        </div>

        {menu.recent.length > 0 && (
          <>
            <div className={styles.section_label}>Recent</div>
            <div className={styles.recent}>
              {menu.recent.map((item) => (
                <Card
                  key={item.filename}
                  className={styles.recent_card}
                  appearance="subtle"
                  onClick={() => { hide_menu(); api.open_doc(item.filename); }}
                >
                  <CardHeader
                    header={
                      <Text weight="semibold" truncate wrap={false}>
                        {item.title.trim() || "Untitled trip"}
                      </Text>
                    }
                    description={
                      <span className={styles.recent_meta}>{item.meta}</span>
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
          className={styles.footer_btn}
          appearance="subtle"
          icon={icon("settings")}
          onClick={() => { hide_menu(); api.open_settings(); }}
        >
          Settings...
        </Button>
      </DrawerFooter>
    </OverlayDrawer>
  );
}

declare global {
  interface Window {
    menu: MenuView | null;
  }
}

window.menu = null;
