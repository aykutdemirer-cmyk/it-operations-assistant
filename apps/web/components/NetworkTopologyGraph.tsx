"use client";

import { useMemo, type MouseEvent } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { Asset } from "@/lib/api";
import { DeviceIcon, GatewayIcon } from "@/lib/deviceIcons";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import styles from "./NetworkTopologyGraph.module.css";

type Dict = (typeof translations)["tr"];

type DeviceNodeData = { asset: Asset; label: string; ip: string };
type HubNodeData = { label: string; count: number };

function subnetOf(ipAddress: string): string {
  const parts = ipAddress.split(".");
  if (parts.length !== 4) return ipAddress;
  return `${parts[0]}.${parts[1]}.${parts[2]}.0/24`;
}

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

function DeviceNodeComponent({ data, selected }: NodeProps) {
  const { t } = useLocale();
  const { asset, label, ip } = data as unknown as DeviceNodeData;
  const online = asset.status === "up";
  return (
    <div
      className={`${styles.deviceNode} ${online ? styles.online : styles.offline} ${selected ? styles.selected : ""}`}
      title={`${label} · ${ip} · ${deviceTypeLabel(asset.device_type, t)}`}
    >
      <Handle type="target" position={Position.Top} className={styles.handle} />
      <div className={styles.iconWrap}>
        {online && <span className={styles.glow} aria-hidden="true" />}
        <DeviceIcon deviceType={asset.device_type} className={styles.icon} />
        <span className={`${styles.statusDot} ${online ? styles.dotUp : styles.dotDown}`} aria-hidden="true" />
      </div>
      <div className={styles.nodeLabel}>{label}</div>
      <div className={styles.nodeIp}>{ip}</div>
      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
}

function HubNodeComponent({ data }: NodeProps) {
  const { label, count } = data as unknown as HubNodeData;
  return (
    <div className={styles.hubNode}>
      <Handle type="target" position={Position.Top} className={styles.handle} />
      <GatewayIcon className={styles.hubIcon} />
      <div className={styles.hubLabel}>{label}</div>
      <div className={styles.hubCount}>{count}</div>
      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
}

const NODE_TYPES = { device: DeviceNodeComponent, hub: HubNodeComponent };

function edgeStyle(online: boolean) {
  return { stroke: online ? "var(--status-up)" : "var(--border-strong)", strokeWidth: online ? 1.6 : 1.2 };
}

/** Bir subnet hub'ının etrafına cihazları dairesel (radial) yerleştirir. */
function placeRing(centerX: number, centerY: number, count: number, minRadius: number) {
  const radius = Math.max(minRadius, 46 * Math.max(count, 1) ** 0.62);
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    return { x: centerX + radius * Math.cos(angle), y: centerY + radius * Math.sin(angle) };
  });
}

/** Faz 38 — assets'i gerçek subnet'lerine göre gruplar; tek subnet
 * varsa (yaygın durum) ortada TEK bir hub + dairesel bir halka, birden
 * fazla subnet varsa ortada bir "kök" düğüm + her subnet için kendi
 * halkasına sahip bir hub (2 seviyeli hiyerarşik/radial düzen). Sabit
 * bir grid/izgara YOK — tamamen gerçek `ip_address`'ten türetilir. */
function buildGraph(assets: Asset[], t: Dict): { nodes: Node[]; edges: Edge[] } {
  const bySubnet = new Map<string, Asset[]>();
  for (const asset of assets) {
    const key = subnetOf(asset.ip_address);
    if (!bySubnet.has(key)) bySubnet.set(key, []);
    bySubnet.get(key)!.push(asset);
  }
  const subnetEntries = [...bySubnet.entries()];
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  function addDeviceRing(hubId: string, centerX: number, centerY: number, list: Asset[]) {
    const positions = placeRing(centerX, centerY, list.length, 190);
    list.forEach((asset, i) => {
      const online = asset.status === "up";
      nodes.push({
        id: asset.id,
        type: "device",
        position: positions[i],
        data: { asset, label: asset.hostname ?? asset.ip_address, ip: asset.ip_address } as never,
      });
      edges.push({
        id: `${hubId}->${asset.id}`,
        source: hubId,
        target: asset.id,
        type: "straight",
        style: edgeStyle(online),
      });
    });
  }

  if (subnetEntries.length <= 1) {
    const [cidr, list] = subnetEntries[0] ?? [t.topology.graph.network, assets];
    nodes.push({
      id: "hub",
      type: "hub",
      position: { x: 0, y: 0 },
      data: { label: cidr, count: list.length } as never,
      draggable: true,
    });
    addDeviceRing("hub", 0, 0, list);
  } else {
    nodes.push({
      id: "root",
      type: "hub",
      position: { x: 0, y: 0 },
      data: { label: t.topology.graph.network, count: assets.length } as never,
    });
    const hubPositions = placeRing(0, 0, subnetEntries.length, 260);
    subnetEntries.forEach(([cidr, list], si) => {
      const hubId = `hub-${cidr}`;
      const { x, y } = hubPositions[si];
      nodes.push({ id: hubId, type: "hub", position: { x, y }, data: { label: cidr, count: list.length } as never });
      edges.push({ id: `root->${hubId}`, source: "root", target: hubId, type: "straight", style: edgeStyle(true) });
      addDeviceRing(hubId, x, y, list);
    });
  }

  return { nodes, edges };
}

type Props = {
  assets: Asset[];
  selectedAssetId: string | null;
  onSelectAsset: (asset: Asset) => void;
};

export function NetworkTopologyGraph({ assets, selectedAssetId, onSelectAsset }: Props) {
  const { t } = useLocale();
  const { nodes, edges } = useMemo(() => buildGraph(assets, t), [assets, t]);

  const styledNodes = useMemo(
    () => nodes.map((n) => (n.id === selectedAssetId ? { ...n, selected: true } : n)),
    [nodes, selectedAssetId]
  );

  return (
    <div className={styles.graphWrap}>
      <ReactFlow
        nodes={styledNodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={(_event: MouseEvent, node: Node) => {
          if (node.type === "device") {
            onSelectAsset((node.data as unknown as DeviceNodeData).asset);
          }
        }}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.2}
        maxZoom={2.5}
      >
        {/* React Flow'un "React Flow" attribution'ı BİLİNÇLİ olarak
            gizlenmedi — ücretsiz/MIT kullanım şartları, Pro aboneliği
            olmadan attribution'ın kaldırılmamasını istiyor. */}
        <Background gap={24} color="var(--border-subtle)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
