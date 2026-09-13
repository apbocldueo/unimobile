import { useEffect } from "react";
import { StudioQueryProvider } from "@/app/providers/StudioQueryProvider";
import { AppRoutes } from "@/app/routes";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

export default function App() {
  useEffect(() => {
    void useStudioRegistryStore.getState().bootstrap();
  }, []);

  return (
    <StudioQueryProvider>
      <AppRoutes />
    </StudioQueryProvider>
  );
}
