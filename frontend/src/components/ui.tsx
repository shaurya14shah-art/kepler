import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Decision, Where } from "../lib/api";

/** Poll an async loader every `ms` (and on demand via the returned reload). */
export function usePoll<T>(load: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    setData(null);
    reload();
    if (!ms) return;
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, reload };
}

export function SevChip({ severity }: { severity: Decision["severity"] }) {
  return <span className={`chip ${severity}`}>{severity}</span>;
}

export function StatusChip({ status }: { status: "ok" | "anomaly" | "stale" | "open" | "resolved" }) {
  const label = { ok: "normal", anomaly: "anomaly", stale: "no data", open: "open", resolved: "resolved" }[status];
  const cls = status === "open" ? "anomaly" : status === "resolved" ? "ok" : status;
  return <span className={`chip ${cls}`}>{label}</span>;
}

export function WhereChips({ where }: { where: Where[] }) {
  const w = where.filter((x) => x.dimension !== "*");
  if (!w.length) return <span className="chip">all segments</span>;
  return (
    <span className="row" style={{ gap: 6 }}>
      {w.map((x) => (
        <span key={`${x.dimension}=${x.value}`} className="chip where">
          {x.dimension}={x.value}
        </span>
      ))}
    </span>
  );
}

/** Pretty JSON with light syntax colouring (no innerHTML). */
export function JsonView({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  const parts = text.split(/("(?:\\.|[^"\\])*"(?:\s*:)?|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g);
  return (
    <pre className="code">
      {parts.map((p, i) => {
        if (/^".*":$/.test(p.replace(/\s/g, ""))) return <span key={i} className="json-key">{p}</span>;
        if (p.startsWith('"')) return <span key={i} className="json-str">{p}</span>;
        if (/^-?\d/.test(p)) return <span key={i} className="json-num">{p}</span>;
        return p;
      })}
    </pre>
  );
}

/** Modal drawer built on <dialog>: showModal() for focus trapping + Esc, light-dismiss via closedby with a fallback. */
export function Drawer({ open, onClose, label, children }: { open: boolean; onClose: () => void; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    d.setAttribute("closedby", "any");
    const onCloseEvt = () => onClose();
    d.addEventListener("close", onCloseEvt);
    // Fallback for browsers without closedby (Safari): close on backdrop clicks
    const onClick = (e: MouseEvent) => {
      if ("closedBy" in HTMLDialogElement.prototype || e.target !== d) return;
      const r = d.getBoundingClientRect();
      const inside = r.top <= e.clientY && e.clientY <= r.bottom && r.left <= e.clientX && e.clientX <= r.right;
      if (!inside) d.close();
    };
    d.addEventListener("click", onClick);
    return () => {
      d.removeEventListener("close", onCloseEvt);
      d.removeEventListener("click", onClick);
    };
  }, [onClose]);
  return (
    <dialog ref={ref} className="drawer" aria-label={label}>
      {open && children}
    </dialog>
  );
}

const ToastCtx = createContext<(msg: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number>(undefined);
  const show = useCallback((m: string) => {
    setMsg(m);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMsg(null), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {msg && (
        <div className="toast" role="status">
          {msg}
        </div>
      )}
    </ToastCtx.Provider>
  );
}

/** Tiny hash router: #/path/segments */
export function useRoute(): string[] {
  const parse = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path: string) => {
  window.location.hash = path;
};
