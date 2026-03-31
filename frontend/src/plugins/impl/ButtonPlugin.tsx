/* Copyright 2026 Marimo. All rights reserved. */

import { type JSX, useEffect } from "react";
import { z } from "zod";
import { KeyboardHotkeys } from "@/components/shortcuts/renderShortcut";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { HTMLCellId } from "@/core/cells/ids";
import { cn } from "@/utils/cn";
import { Button } from "../../components/ui/button";
import { renderHTML } from "../core/RenderHTML";
import type { IPlugin, IPluginProps, Setter } from "../types";
import { type Intent, zodIntent } from "./common/intent";

/**
 * Tracks which cells have already auto-fired for "once" mode.
 * Module-level so it persists across cell re-executions (preventing re-fire)
 * but resets on page reload (allowing fire on each notebook load).
 */
const autoRunFiredCells = new Set<string>();

interface Data {
  label: string;
  kind: Intent;
  disabled: boolean;
  fullWidth: boolean;
  tooltip?: string;
  keyboardShortcut?: string;
  autoRun: false | "once" | "always";
}

export class ButtonPlugin implements IPlugin<number, Data> {
  tagName = "marimo-button";

  validator = z.object({
    label: z.string(),
    kind: zodIntent,
    disabled: z.boolean().default(false),
    fullWidth: z.boolean().default(false),
    tooltip: z.string().optional(),
    keyboardShortcut: z.string().optional(),
    autoRun: z
      .union([z.literal(false), z.enum(["once", "always"])])
      .default(false),
  });

  render(props: IPluginProps<number, Data>): JSX.Element {
    return <ButtonComponent {...props} />;
  }
}

interface ButtonComponentProps extends IPluginProps<number, Data> {}

const ButtonComponent = ({
  data: {
    disabled,
    kind,
    label,
    fullWidth,
    tooltip,
    keyboardShortcut,
    autoRun,
  },
  setValue,
  host,
}: ButtonComponentProps): JSX.Element => {
  useAutoRun({ autoRun, setValue, host });

  // value counts number of times button was clicked
  const button = (
    <Button
      data-testid="marimo-plugin-button"
      variant={kindToButtonVariant(kind)}
      disabled={disabled}
      size="xs"
      keyboardShortcut={keyboardShortcut}
      className={cn({
        "w-full": fullWidth,
        "w-fit": !fullWidth,
      })}
      onClick={(evt) => {
        if (disabled) {
          return;
        }
        evt.stopPropagation();
        setValue((v) => v + 1);
      }}
      type="submit"
    >
      {renderHTML({ html: label })}
    </Button>
  );

  const tooltipContent =
    keyboardShortcut && !tooltip ? (
      <KeyboardHotkeys shortcut={keyboardShortcut} />
    ) : (
      tooltip
    );

  if (tooltipContent) {
    return (
      <TooltipProvider>
        <Tooltip content={tooltipContent} delayDuration={200}>
          {button}
        </Tooltip>
      </TooltipProvider>
    );
  }

  return button;
};

/**
 * Auto-fire the button on mount based on the autoRun mode.
 *
 * - "always": fires every time the component mounts (every cell execution).
 * - "once": fires only on the first mount per cell per page session.
 *   Uses a module-level Set keyed by cell ID so it survives cell re-executions
 *   but resets on page reload.
 */
function useAutoRun(opts: {
  autoRun: Data["autoRun"];
  setValue: Setter<number>;
  host: HTMLElement;
}) {
  useEffect(() => {
    const { autoRun, setValue, host } = opts;
    if (!autoRun) {
      return;
    }

    if (autoRun === "always") {
      setValue((v) => v + 1);
      return;
    }

    // "once" — fire only if this cell hasn't auto-fired yet this session
    const cellId =
      HTMLCellId.findElementThroughShadowDOMs(host)?.id ?? undefined;
    if (cellId && !autoRunFiredCells.has(cellId)) {
      autoRunFiredCells.add(cellId);
      setValue((v) => v + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

function kindToButtonVariant(kind: Intent) {
  switch (kind) {
    case "neutral":
      return "secondary";
    case "danger":
      return "destructive";
    case "warn":
      return "warn";
    case "success":
      return "success";
  }
}
