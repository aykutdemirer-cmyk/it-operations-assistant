"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import "@xterm/xterm/css/xterm.css";

import { pamSshWebSocketUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./SshTerminal.module.css";

type Phase = "connecting" | "connected" | "closed" | "error";

type Props = {
  assetId: string;
};

/** Faz 46 — Zero-Knowledge PAM SSH terminal. `SshTerminal.tsx`'in
 * (Faz 35) AKSİNE, kullanıcıdan kullanıcı adı/parola İSTEMEZ — kimlik
 * bilgisi backend'de, PAM kuralına göre ÇÖZÜLÜP doğrudan sunucuya
 * enjekte edilir (bkz. `apps/api/app/routes/pam_ssh.py`); bu component
 * hiçbir kimlik bilgisi DEĞERİ görmez/tutmaz. Bağlantı mount olur
 * olmaz otomatik başlar (ayrı bir "giriş formu" adımı YOK)."""*/
export function PamSshTerminal({ assetId }: Props) {
  const { t } = useLocale();
  const { token } = useAuth();
  const s = t.sshTerminal;

  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<import("@xterm/xterm").Terminal | null>(null);
  const fitAddonRef = useRef<import("@xterm/addon-fit").FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [phase, setPhase] = useState<Phase>("connecting");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const connect = useCallback(async () => {
    if (!containerRef.current || !token) return;

    const { Terminal } = await import("@xterm/xterm");
    const { FitAddon } = await import("@xterm/addon-fit");

    if (!termRef.current) {
      const term = new Terminal({ cursorBlink: true, convertEol: true, fontSize: 14 });
      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(containerRef.current);
      fitAddon.fit();
      termRef.current = term;
      fitAddonRef.current = fitAddon;
    }
    const term = termRef.current;

    const ws = new WebSocket(pamSshWebSocketUrl(assetId, token));
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "connect", cols: term.cols, rows: term.rows }));
    };

    ws.onmessage = (evt) => {
      const message = JSON.parse(evt.data);
      if (message.type === "connected") {
        setPhase("connected");
        term.focus();
      } else if (message.type === "data") {
        term.write(message.data);
      } else if (message.type === "error") {
        setPhase("error");
        setErrorMessage(message.message);
      } else if (message.type === "closed") {
        setPhase("closed");
      }
    };

    ws.onerror = () => {
      setPhase("error");
      setErrorMessage(s.connectionError);
    };

    ws.onclose = () => {
      setPhase((prev) => (prev === "connected" ? "closed" : prev));
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });
  }, [assetId, token, s.connectionError]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      termRef.current?.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleResize = () => {
      const term = termRef.current;
      const fitAddon = fitAddonRef.current;
      const ws = wsRef.current;
      if (!term || !fitAddon) return;
      fitAddon.fit();
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className={styles.wrap}>
      {phase === "connecting" && <p className={styles.status}>{s.connecting}</p>}

      {phase === "error" && (
        <div className={styles.errorBox}>
          <p>{errorMessage}</p>
        </div>
      )}

      {phase === "closed" && <p className={styles.status}>{s.sessionClosed}</p>}

      <div
        ref={containerRef}
        className={styles.terminalContainer}
        style={{ display: phase === "connected" || phase === "closed" ? "block" : "none" }}
      />
    </div>
  );
}
