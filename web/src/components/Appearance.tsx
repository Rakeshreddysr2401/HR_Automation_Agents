import { ACCENTS, useTheme, type ThemeChoice } from "../state/themeStore";
import { Segmented, IconButton } from "./ui";
import { IconCompact, IconMonitor, IconMoon, IconRows, IconSun } from "./icons";

/**
 * The appearance controls.
 *
 * Deliberately three separate controls rather than a settings page. A console
 * someone stares at for a full working day gets adjusted constantly — dark at
 * dusk, compact once the queue is long — and burying that two clicks deep means
 * it never gets used.
 */
export function Appearance() {
  const { theme, accent, density, setTheme, setAccent, toggleDensity } = useTheme();

  return (
    <div className="flex items-center gap-1.5">
      <AccentPicker accent={accent} onChange={setAccent} />

      <IconButton
        title={density === "compact" ? "Comfortable rows" : "Compact rows"}
        active={density === "compact"}
        onClick={toggleDensity}
      >
        {density === "compact" ? <IconCompact /> : <IconRows />}
      </IconButton>

      <Segmented<ThemeChoice>
        label="Colour theme"
        value={theme}
        onChange={setTheme}
        options={[
          { id: "light", label: <IconSun />, title: "Light" },
          { id: "dark", label: <IconMoon />, title: "Dark" },
          { id: "system", label: <IconMonitor />, title: "Follow the system" },
        ]}
      />
    </div>
  );
}

/* The same gradient formula tokens.css uses, evaluated per accent, so each
   swatch is literally the colour it will apply rather than an approximation. */
const SWATCH: Record<string, string> = {
  indigo: "linear-gradient(135deg, oklch(0.6 0.17 227), oklch(0.53 0.17 262), oklch(0.58 0.18 302))",
  cyan: "linear-gradient(135deg, oklch(0.6 0.13 175), oklch(0.53 0.13 210), oklch(0.58 0.14 250))",
  violet: "linear-gradient(135deg, oklch(0.6 0.16 265), oklch(0.53 0.16 300), oklch(0.58 0.17 340))",
  emerald: "linear-gradient(135deg, oklch(0.6 0.13 130), oklch(0.53 0.13 165), oklch(0.58 0.14 205))",
};

function AccentPicker({
  accent,
  onChange,
}: {
  accent: string;
  onChange: (id: (typeof ACCENTS)[number]["id"]) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Accent colour"
      className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-line bg-sunken px-1.5 py-1"
    >
      {ACCENTS.map((option) => (
        <button
          key={option.id}
          type="button"
          title={`${option.label} accent`}
          aria-label={`${option.label} accent`}
          aria-pressed={accent === option.id}
          onClick={() => onChange(option.id)}
          className="size-3 rounded-full transition-transform duration-[var(--dur-fast)] hover:scale-125"
          style={{
            background: SWATCH[option.id],
            boxShadow: accent === option.id ? "0 0 0 2px var(--ring)" : undefined,
          }}
        />
      ))}
    </div>
  );
}
