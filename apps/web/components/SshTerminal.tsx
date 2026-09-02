"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import "@xterm/xterm/css/xterm.css";

import { agentSshWebSocketUrl } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./SshTerminal.module.css";

type Phase = "login" | "connecting" | "connected" | "closed" | "error";

type Props = {
  agentId: string;
};

/** Faz 35 — Web SSH Terminal. Kimlik bilgisi (kullanıcı adı/parola)
 * YALNIZCA bu component'in state'inde, bağlantı kurulana kadar durur —
 * hiçbir yerde (localStorage/URL/log) KALICI olarak saklanmaz; WS
 * bağlantısı kapanınca React state'i de component unmount ile birlikte
 * kaybolur. `@xterm/xterm` yalnızca istemci tarafında (mount sonrası)
 * yüklenir — SSR uyumluluğu için. */
export function SshTerminal({ agentId }: Props) {
  const { t } = useLocale();
  const s = t.sshTerminal;

  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<import("@xterm/xterm").Terminal | null>(null);
  const fitAddonRef = useRef<import("@xterm/addon-fit").FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [phase, setPhase] = useState<Phase>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      termRef.current?.dispose();
    };
  }, []);

  const connect = useCallback(
    async (evt: React.FormEvent) => {
      evt.preventDefault();
      if (!containerRef.current) return;
      setPhase("connecting");
      setErrorMessage(null);

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

      const ws = new WebSocket(agentSshWebSocketUrl(agentId));
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "connect",
            username,
            password,
            cols: term.cols,
            rows: term.rows,
          })
        );
      };

      ws.onmessage = (evt) => {
        const message = JSON.parse(evt.data);
        if (message.type === "connected") {
          setPhase("connected");
          setPassword("");
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
    },
    [agentId, username, password, s.connectionError]
  );

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
      {phase === "login" && (
        <form className={styles.loginForm} onSubmit={connect}>
          <h2 className={styles.loginTitle}>{s.title}</h2>
          <label className={styles.field}>
            {s.username}
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </label>
          <label className={styles.field}>
            {s.password}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" className={styles.connectButton}>
            {s.connect}
          </button>
          <p className={styles.hint}>{s.credentialHint}</p>
        </form>
      )}

      {phase === "connecting" && <p className={styles.status}>{s.connecting}</p>}

      {phase === "error" && (
        <div className={styles.errorBox}>
          <p>{errorMessage}</p>
          <button type="button" className={styles.connectButton} onClick={() => setPhase("login")}>
            {s.tryAgain}
          </button>
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
