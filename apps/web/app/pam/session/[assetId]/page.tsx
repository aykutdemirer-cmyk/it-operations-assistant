"use client";

import { useParams } from "next/navigation";

import { GuacamoleRdpViewer } from "@/components/GuacamoleRdpViewer";
import { RequirePermission } from "@/components/RequirePermission";

// Faz 48 — bu sayfa KASITLI olarak `shared.module.css::page`
// dolgusunu/sidebar-yanı düzenini KULLANMIYOR: `GuacamoleRdpViewer`
// kendi `position: fixed; inset: 0` tam-ekran, dikkat dağıtmayan
// ("distraction-free") oturum katmanını render ediyor — CyberArk/
// Teleport'un oturum ekranlarıyla AYNI tasarım ilkesi.
export default function PamRdpSessionPage() {
  const params = useParams<{ assetId: string }>();

  return (
    <RequirePermission permission="PAM_ACCESS">
      <GuacamoleRdpViewer assetId={params.assetId} />
    </RequirePermission>
  );
}
