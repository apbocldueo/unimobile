import { useEffect } from "react";
import { StudioQueryProvider } from "./providers/StudioQueryProvider";
import { AppRoutes } from "./routes";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

/** Bootstrap existing Studio resources only after a workspace route is entered. */
export default function StudioApplication() {
  useEffect(() => {
    void useStudioRegistryStore.getState().bootstrap();
  }, []);

  return <StudioQueryProvider><AppRoutes /></StudioQueryProvider>;
}
