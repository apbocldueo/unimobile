import { describe, expect, it } from "vitest";
import { runtimeConfigurationLabel } from "./remediation";
import type { RuntimeEnvironmentReadiness } from "./runtimeReadiness.schema";

const ready: RuntimeEnvironmentReadiness = {
  schemaVersion: 1, ready: true, providers: [], secrets: [], deviceProfiles: [], diagnostics: [],
};

describe("configuration status evidence", () => {
  it("does not show cached success after an error or during refresh", () => {
    expect(runtimeConfigurationLabel(ready, true, false)).toBe("无法读取运行配置");
    expect(runtimeConfigurationLabel(ready, false, true)).toBe("正在检查运行配置…");
    expect(runtimeConfigurationLabel(ready, false, false)).toBe("运行配置已就绪");
  });
  it("identifies missing device configuration rather than device connectivity", () => {
    expect(runtimeConfigurationLabel({ ...ready, ready: false, diagnostics: [{
      code: "studio.readiness.profile_empty", category: "profile", message: "No profile",
      subjectIdentity: null, nodeId: null, remediationKey: "configure-device-profile",
    }] }, false, false)).toBe("未加载设备配置");
  });
});
