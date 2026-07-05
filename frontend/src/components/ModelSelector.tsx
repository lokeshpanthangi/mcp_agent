import { useEffect, useRef, useState } from "react";
import { ModelInfo } from "../api";

interface Props {
  model: string;
  models: ModelInfo[];
  onSelect: (name: string) => void;
}

export default function ModelSelector({ model, models, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = models.find((m) => m.name === model);

  return (
    <div className="model-select" ref={ref}>
      <button className="model-select-btn" onClick={() => setOpen((o) => !o)}>
        <span className="model-select-name">{model || "Select model"}</span>
        {current?.reasoning && (
          <span className="reason-dot" title="Supports reasoning">✦</span>
        )}
        <span className="model-select-caret">▾</span>
      </button>
      {open && (
        <div className="model-menu">
          {models.length === 0 && <div className="model-menu-empty">No models found</div>}
          {models.map((m) => (
            <button
              key={m.name}
              className={`model-option ${m.name === model ? "active" : ""}`}
              onClick={() => {
                onSelect(m.name);
                setOpen(false);
              }}
            >
              <span className="model-option-name">{m.name}</span>
              {m.reasoning && <span className="reason-badge">✦ reasoning</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
