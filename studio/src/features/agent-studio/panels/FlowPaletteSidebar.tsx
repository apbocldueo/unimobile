import { useCallback, useState } from "react";
import {
  FLOW_COMPONENT_DRAG_MIME,
  FLOW_NODE_CATALOG,
  FLOW_NODE_GROUP_LABELS,
  type FlowComponentDef,
  type FlowComponentGroup,
} from "@/components/flow-studio-cards";
import { IconChevronDown } from "@/components/icons/StudioIcons";

function handleDragStart(e: React.DragEvent, component: FlowComponentDef) {
  e.dataTransfer.setData(FLOW_COMPONENT_DRAG_MIME, component.id);
  e.dataTransfer.effectAllowed = "copy";
}

const GROUP_ORDER: FlowComponentGroup[] = ["core", "io", "flow"];

function initialOpenState(): Record<FlowComponentGroup, boolean> {
  return { core: false, io: false, flow: false };
}

export function FlowPaletteSidebar() {
  const [openByGroup, setOpenByGroup] = useState<Record<FlowComponentGroup, boolean>>(initialOpenState);

  const toggleGroup = useCallback((key: FlowComponentGroup) => {
    setOpenByGroup((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return (
    <aside className="flow-side-panel" aria-label="组件库">
      {GROUP_ORDER.map((groupKey) => {
        const expanded = openByGroup[groupKey];
        const headingId = `flow-palette-group-${groupKey}-heading`;
        const panelId = `flow-palette-group-${groupKey}-panel`;
        return (
          <div key={groupKey} className="flow-panel-group">
            <button
              type="button"
              className="flow-panel-group-toggle"
              id={headingId}
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={() => toggleGroup(groupKey)}
            >
              <span className="flow-panel-group-chevron" aria-hidden data-expanded={expanded}>
                <IconChevronDown size={16} strokeWidth={2.25} />
              </span>
              <span className="flow-panel-group-title">{FLOW_NODE_GROUP_LABELS[groupKey]}</span>
            </button>
            <div
              id={panelId}
              className="flow-panel-components"
              role="region"
              aria-labelledby={headingId}
              hidden={!expanded}
            >
              {FLOW_NODE_CATALOG[groupKey].map((comp) => (
                <div
                  key={comp.id}
                  className="flow-component-card"
                  draggable
                  onDragStart={(e) => handleDragStart(e, comp)}
                >
                  <span className="flow-comp-icon" aria-hidden>
                    {comp.icon}
                  </span>
                  <div className="flow-comp-info">
                    <div className="flow-comp-label">{comp.label}</div>
                    <div className="flow-comp-desc">{comp.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </aside>
  );
}
