"use client";

import { useState } from "react";

import type { PortResult } from "@/lib/api";
import { classifyPortRisk, type PortRisk } from "@/lib/portRisk";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./PortBadges.module.css";

const MAX_VISIBLE = 3;
const RISK_ORDER: PortRisk[] = ["HIGH", "MEDIUM", "LOW"];

type Props = {
  ports: PortResult[];
};

/** Açık port listesini yatay, sarmalanan (`flex-wrap`) rozetler olarak
 * gösterir — en fazla 3 tanesi görünür, fazlası "+X daha" rozetiyle
 * özetlenir. O rozetin üzerine gelindiğinde/tıklandığında tüm portları
 * risk seviyesine göre gruplanmış bir popover açar. */
export function PortBadges({ ports }: Props) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  if (ports.length === 0) return <span>-</span>;

  const visible = ports.slice(0, MAX_VISIBLE);
  const hiddenCount = ports.length - visible.length;

  const grouped = RISK_ORDER.map((risk) => ({
    risk,
    ports: ports.filter((p) => classifyPortRisk(p.port) === risk),
  })).filter((g) => g.ports.length > 0);

  return (
    <span className={styles.wrap}>
      <span className={styles.chipList}>
        {visible.map((p) => (
          <span key={p.port} className={`${styles.chip} ${styles[`risk-${classifyPortRisk(p.port)}`]}`}>
            {p.port}
          </span>
        ))}
        {hiddenCount > 0 && (
          <span
            className={styles.moreChip}
            tabIndex={0}
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
            onClick={(e) => {
              e.stopPropagation();
              setOpen((v) => !v);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setOpen((v) => !v);
              }
            }}
          >
            +{hiddenCount} {t.assets.morePorts}
          </span>
        )}
      </span>

      {open && hiddenCount > 0 && (
        <div className={styles.popover} onClick={(e) => e.stopPropagation()}>
          {grouped.map((group) => (
            <div key={group.risk} className={styles.popoverGroup}>
              <span className={`${styles.popoverGroupLabel} ${styles[`risk-${group.risk}`]}`}>
                {t.risk[group.risk.toLowerCase() as "high" | "medium" | "low"]}
              </span>
              <span className={styles.popoverPorts}>{group.ports.map((p) => p.port).join(", ")}</span>
            </div>
          ))}
        </div>
      )}
    </span>
  );
}
