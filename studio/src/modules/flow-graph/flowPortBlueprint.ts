import type { FlowDataType } from "./flowDataTypes";
import { FLOW_STUDIO_PORT_BLUEPRINTS_BY_ID } from "@/components/flow-studio-cards/blueprintIndex";

export type PortKind = "input" | "output";

/** 端口模板（不含实例 portId，创建节点时生成）。 */
export type PortBlueprint = {
  role: string;
  portName: string;
  portKind: PortKind;
  /** 输出端口：单一发射类型；输入端口：可接受的类型集合。 */
  dataTypes: FlowDataType[];
  /** 0–1，沿左/右边缘的垂直位置（0.5 居中）。 */
  slot: number;
};

export type FlowPortInstance = PortBlueprint & {
  portId: string;
};

function pid(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 由蓝图生成端口实例（画布节点与 `FlowStudioPaletteShell` 共用）。 */
export function instantiateBlueprints(ports: PortBlueprint[], prefix: string): FlowPortInstance[] {
  return ports.map((p) => ({ ...p, portId: pid(prefix) }));
}

export function getBlueprintForComponent(componentId: string): PortBlueprint[] {
  return FLOW_STUDIO_PORT_BLUEPRINTS_BY_ID[componentId] ?? [];
}

export function createPortsForComponent(componentId: string, idPrefix: string): FlowPortInstance[] {
  return instantiateBlueprints(getBlueprintForComponent(componentId), idPrefix);
}
