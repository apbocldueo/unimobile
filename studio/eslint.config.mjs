import js from "@eslint/js";
import tseslint from "typescript-eslint";

const reverseLayerPatterns = {
  shared: ["@/entities/**", "@/features/**", "@/widgets/**", "@/pages/**", "@/app/**"],
  entities: ["@/features/**", "@/widgets/**", "@/pages/**", "@/app/**", "@xyflow/react"],
  features: ["@/widgets/**", "@/pages/**", "@/app/**"],
  widgets: ["@/pages/**", "@/app/**"],
  pages: ["@/app/**"],
};

const deepSlicePatterns = ["@/entities/*/**", "@/features/*/**", "@/widgets/*/**", "@/pages/*/**"];

function layerRule(patterns) {
  return {
    "no-restricted-imports": [
      "error",
      {
        patterns: [...patterns, ...deepSlicePatterns].map((group) => ({
          group: [group],
          message: "Import violates the Studio app → pages → widgets → features → entities → shared dependency direction.",
        })),
      },
    ],
  };
}

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  {
    files: ["src/shared/**/*.{ts,tsx}"],
    rules: layerRule(reverseLayerPatterns.shared),
  },
  {
    files: ["src/entities/**/*.{ts,tsx}"],
    rules: layerRule(reverseLayerPatterns.entities),
  },
  {
    files: [
      "src/features/agent-builder/**/*.{ts,tsx}",
      "src/features/trajectory-replay/**/*.{ts,tsx}",
      "src/features/run-inspector/**/*.{ts,tsx}",
      "src/features/virtual-phone/**/*.{ts,tsx}",
      "src/features/live-run-session/**/*.{ts,tsx}",
      "src/features/experiment-composer/**/*.{ts,tsx}",
      "src/features/benchmark-experiment-monitor/**/*.{ts,tsx}",
      "src/features/benchmark-reporting/**/*.{ts,tsx}",
    ],
    rules: layerRule(reverseLayerPatterns.features),
  },
  {
    files: ["src/widgets/**/*.{ts,tsx}"],
    rules: layerRule(reverseLayerPatterns.widgets),
  },
  {
    files: [
      "src/pages/agent-builder/**/*.{ts,tsx}",
      "src/pages/agent-run/**/*.{ts,tsx}",
      "src/pages/run-history/**/*.{ts,tsx}",
      "src/pages/run-replay/**/*.{ts,tsx}",
      "src/pages/benchmarks/**/*.{ts,tsx}",
      "src/pages/benchmark-detail/**/*.{ts,tsx}",
      "src/pages/experiment-create/**/*.{ts,tsx}",
      "src/pages/experiment-monitor/**/*.{ts,tsx}",
      "src/pages/experiment-report/**/*.{ts,tsx}",
    ],
    rules: layerRule(reverseLayerPatterns.pages),
  },
);
