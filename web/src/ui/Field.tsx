import { useId } from "react";

interface FieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  hint?: string;
}

/** A slider with an editable number next to it, so both rough and exact input are easy. */
export function Field({ label, value, onChange, min, max, step = 1, unit, hint }: FieldProps) {
  const id = useId();
  const commit = (raw: string) => {
    const n = Number(raw);
    if (raw !== "" && Number.isFinite(n)) onChange(Math.min(max, Math.max(min, n)));
  };
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="field-controls">
        <input
          type="range"
          aria-label={`${label} (controle deslizante)`}
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => {
            commit(e.target.value);
          }}
        />
        <span className="field-number">
          <input
            id={id}
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => {
              commit(e.target.value);
            }}
          />
          {unit && <span className="unit">{unit}</span>}
        </span>
      </div>
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
}

export function Toggle({ label, checked, onChange, hint }: ToggleProps) {
  return (
    <div className="field">
      <label className="toggle">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => {
            onChange(e.target.checked);
          }}
        />
        <span>{label}</span>
      </label>
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}
