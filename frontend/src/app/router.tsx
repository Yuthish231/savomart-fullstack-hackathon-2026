import type { ReactNode } from "react";
import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import type { Role } from "@/api/types";
import { HOME } from "@/app/nav";
import { AppShell } from "@/components/AppShell";
import { LoginPage } from "@/routes/auth/LoginPage";
import { ExplorePage } from "@/routes/bdm/ExplorePage";
import {
  AddPropertyPage,
  BdePropertiesPage,
  BdeTasksPage,
  BdmStudiesPage,
  PipelinePage,
  ReportsPage,
  SeAssignmentsPage,
  SmInboxPage,
  SmStudiesPage,
} from "@/routes/placeholders";
import { useAuth } from "@/stores/auth";

function RequireAuth({ children }: { children: ReactNode }) {
  const user = useAuth((s) => s.user);
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

/** UX guard only; the API enforces roles on every request. */
function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const user = useAuth((s) => s.user)!;
  return user.role === role ? <>{children}</> : <Navigate to={HOME[user.role]} replace />;
}

function HomeRedirect() {
  const user = useAuth((s) => s.user);
  return <Navigate to={user ? HOME[user.role] : "/login"} replace />;
}

const section = (role: Role, children: { path: string; element: ReactNode }[]) => ({
  path: role.toLowerCase(),
  element: (
    <RequireRole role={role}>
      <OutletPassthrough />
    </RequireRole>
  ),
  children,
});

function OutletPassthrough() {
  return <Outlet />;
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      section("BDM", [
        { path: "explore", element: <ExplorePage /> },
        { path: "reports", element: <ReportsPage /> },
        { path: "pipeline", element: <PipelinePage /> },
        { path: "studies", element: <BdmStudiesPage /> },
      ]),
      section("BDE", [
        { path: "tasks", element: <BdeTasksPage /> },
        { path: "new", element: <AddPropertyPage /> },
        { path: "properties", element: <BdePropertiesPage /> },
      ]),
      section("SM", [
        { path: "inbox", element: <SmInboxPage /> },
        { path: "studies", element: <SmStudiesPage /> },
      ]),
      section("SE", [{ path: "assignments", element: <SeAssignmentsPage /> }]),
      { path: "*", element: <HomeRedirect /> },
    ],
  },
]);
