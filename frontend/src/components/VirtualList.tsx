// Fixed-height virtual list: only the rows in view (plus a small overscan) are in the DOM,
// so a 1000-line session scrolls as cheaply as a 20-line one.

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface Props<T> {
  items: T[];
  rowHeight: number;
  selected: number | null;
  onSelect: (index: number) => void;
  onKeyEscape?: () => void;
  renderRow: (item: T, index: number, selected: boolean) => ReactNode;
  label: string;
  idPrefix: string;
  overscan?: number;
}

export function VirtualList<T>({ items, rowHeight, selected, onSelect, onKeyEscape, renderRow, label, idPrefix, overscan = 8 }: Props<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(400);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setHeight(el.clientHeight));
    ro.observe(el);
    setHeight(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  // Keep the selected row in view when it changes from elsewhere (timeline, keyboard)
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || selected === null) return;
    const top = selected * rowHeight;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + rowHeight > el.scrollTop + el.clientHeight) el.scrollTop = top + rowHeight - el.clientHeight;
  }, [selected, rowHeight]);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (el) setScroll(el.scrollTop);
  }, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!items.length) return;
    const page = Math.max(1, Math.floor(height / rowHeight) - 1);
    const cur = selected ?? items.length - 1;
    const keys: Record<string, number> = { ArrowDown: cur + 1, ArrowUp: cur - 1, PageDown: cur + page, PageUp: cur - page, Home: 0, End: items.length - 1 };
    if (e.key in keys) {
      e.preventDefault();
      onSelect(Math.max(0, Math.min(items.length - 1, keys[e.key])));
    } else if (e.key === "Escape" && onKeyEscape) {
      e.preventDefault();
      onKeyEscape();
    }
  };

  const first = Math.max(0, Math.floor(scroll / rowHeight) - overscan);
  const last = Math.min(items.length, Math.ceil((scroll + height) / rowHeight) + overscan);
  const rows: ReactNode[] = [];
  for (let i = first; i < last; i++) {
    rows.push(
      <div
        key={i}
        id={`${idPrefix}-${i}`}
        role="option"
        aria-selected={selected === i}
        className={`vrow${selected === i ? " is-selected" : ""}`}
        style={{ transform: `translateY(${i * rowHeight}px)`, height: rowHeight }}
        onClick={() => onSelect(i)}
      >
        {renderRow(items[i], i, selected === i)}
      </div>,
    );
  }
  return (
    <div
      ref={ref}
      className="vlist"
      role="listbox"
      tabIndex={0}
      aria-label={label}
      aria-activedescendant={selected !== null && selected >= first && selected < last ? `${idPrefix}-${selected}` : undefined}
      onScroll={onScroll}
      onKeyDown={onKey}
    >
      <div className="vlist-inner" style={{ height: items.length * rowHeight }}>
        {rows}
      </div>
    </div>
  );
}
