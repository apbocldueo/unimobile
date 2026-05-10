/** 第六章：顶部导航模块（可由 /studio/nav-modules 返回） */
export type StudioNavModuleDTO = {
  id: string;
  name: string;
  /** 与前端图标表映射，如 bot / lineChart / history / settings */
  iconKey: string;
  order: number;
  /** 路由 path，需与 App 内已注册路由一致（首期仅开放四模块） */
  path: string;
  disabled?: boolean;
  /** 权限：false 时与 disabled 同效，不可点击 */
  allowed?: boolean;
};

/** 侧栏入口占位结构（后续可驱动各模块侧栏） */
export type StudioSidebarItemDTO = {
  id: string;
  label: string;
  iconKey?: string;
};

/** 模块配置（/studio/module-config?moduleId=） */
export type StudioModuleConfigDTO = {
  moduleId: string;
  permission: "allow" | "deny";
  sidebarItems: StudioSidebarItemDTO[];
};
