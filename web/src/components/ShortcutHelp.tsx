import { useStore } from "../state/store";
import { Modal, ModalHeader } from "./ui";

const SECTIONS: { title: string; rows: [string[], string][] }[] = [
  {
    title: "Anywhere",
    rows: [
      [["⌘", "K"], "Command palette"],
      [["?"], "This sheet"],
      [["esc"], "Close whatever is open"],
    ],
  },
  {
    title: "Working the review queue",
    rows: [
      [["j"], "Next question"],
      [["k"], "Previous question"],
      [["1"], "Pick the first option — 1 to 9 for the rest"],
      [["u"], "Undo the answer on the focused card"],
      [["⌘", "↵"], "Apply every staged answer and re-run"],
    ],
  },
];

/** The shortcuts, spelled out. The queue is meant to be worked from the
 *  keyboard, and a shortcut nobody can find is a shortcut nobody uses. */
export function ShortcutHelp() {
  const { helpOpen, setHelp } = useStore();
  return (
    <Modal open={helpOpen} onClose={() => setHelp(false)} label="Keyboard shortcuts">
      <ModalHeader title="Keyboard shortcuts" onClose={() => setHelp(false)} />
      <div className="space-y-4 p-4">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <h3 className="mb-1.5 text-[var(--text-xs)] tracking-wide text-faint uppercase">
              {section.title}
            </h3>
            <ul className="space-y-1">
              {section.rows.map(([keys, description]) => (
                <li key={description} className="flex items-center gap-3 text-[var(--text-base)]">
                  <span className="flex w-24 shrink-0 gap-1">
                    {keys.map((key) => (
                      <kbd key={key}>{key}</kbd>
                    ))}
                  </span>
                  <span className="text-muted">{description}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="border-t border-line pt-3 text-[var(--text-xs)] leading-relaxed text-faint">
          Answering with a number advances to the next card automatically — a queue of forty is
          meant to be worked in one pass, not clicked through.
        </p>
      </div>
    </Modal>
  );
}
