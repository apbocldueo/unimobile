import { Navigate, useLocation } from "react-router-dom";

/** Redirect the legacy Builder entry to the one authoritative Agent Library. */
export function AgentBuilderEntryPage() {
  const location = useLocation();
  return <Navigate to={{ pathname: "/agents", search: location.search }} replace />;
}
