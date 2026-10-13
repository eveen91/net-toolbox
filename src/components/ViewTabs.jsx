import React from "react";

export default function ViewTabs({ items, value, onChange, label = "Views" }) {
  return <div className="nt-view-tabs" role="group" aria-label={label}>
    {items.map((item) => <button key={item.id} type="button" className={value === item.id ? "active" : ""}
      aria-pressed={value === item.id} onClick={() => onChange(item.id)}>{item.label}</button>)}
  </div>;
}
