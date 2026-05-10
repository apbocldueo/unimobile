import { useEffect } from "react";
import { AppRoutes } from "@/app/routes";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

export default function App() {
  useEffect(() => {
    void useStudioRegistryStore.getState().bootstrap();
  }, []);

  return <AppRoutes />;
}
