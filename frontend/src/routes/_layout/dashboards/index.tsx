import { createFileRoute } from "@tanstack/react-router"
import { ManageDashboardsPage } from "@/components/Dashboard/UserDashboards/ManageDashboardsPage"
import { APP_NAME } from "@/utils"

export const Route = createFileRoute("/_layout/dashboards/")({
  component: ManageDashboardsPage,
  head: () => ({
    meta: [
      {
        title: `Manage Dashboards - ${APP_NAME}`,
      },
    ],
  }),
})
