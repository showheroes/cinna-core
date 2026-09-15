import type { Table } from "@tanstack/react-table"
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export const DEFAULT_PAGE_SIZE = 30
export const PAGE_SIZE_OPTIONS = [10, 30, 50, 100]

interface DataTablePaginationProps<TData> {
  table: Table<TData>
  /**
   * Rows across every page. Defaults to the table's own row count, which is
   * only the current page when the server does the slicing.
   */
  total?: number
  /** The noun after the count: "Showing 1 to 30 of 120 entries". */
  itemLabel?: string
  /**
   * Offer "Rows per page". Off for a server-paged list whose owner cannot
   * refetch at another size — the pick would otherwise be dropped and only
   * the page index derived from it would reach the server.
   */
  showPageSize?: boolean
}

/**
 * The pager footer for any TanStack table.
 *
 * Hidden only on the first page of a list that could not be paged at all. Hiding
 * it whenever the current page held everything took "Rows per page" away with
 * it: pick a size larger than the list and the footer vanished, with no way back.
 */
export function DataTablePagination<TData>({
  table,
  total,
  itemLabel = "entries",
  showPageSize = true,
}: DataTablePaginationProps<TData>) {
  const { pageIndex, pageSize } = table.getState().pagination
  const rowCount = total ?? table.getRowCount()

  const pageable = showPageSize
    ? rowCount > PAGE_SIZE_OPTIONS[0]
    : table.getPageCount() > 1
  if (!pageable && pageIndex === 0) return null

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border-t bg-muted/20">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="text-sm text-muted-foreground">
          Showing {Math.min(pageIndex * pageSize + 1, rowCount)} to{" "}
          {Math.min((pageIndex + 1) * pageSize, rowCount)} of{" "}
          <span className="font-medium text-foreground">{rowCount}</span>{" "}
          {itemLabel}
        </div>
        {showPageSize && (
          <div className="flex items-center gap-x-2">
            <p className="text-sm text-muted-foreground">Rows per page</p>
            <Select
              value={`${pageSize}`}
              onValueChange={(value) => {
                table.setPageSize(Number(value))
              }}
            >
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue placeholder={pageSize} />
              </SelectTrigger>
              <SelectContent side="top">
                {PAGE_SIZE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={`${option}`}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-x-6">
        <div className="flex items-center gap-x-1 text-sm text-muted-foreground">
          <span>Page</span>
          <span className="font-medium text-foreground">{pageIndex + 1}</span>
          <span>of</span>
          <span className="font-medium text-foreground">
            {table.getPageCount()}
          </span>
        </div>

        <div className="flex items-center gap-x-1">
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only">Go to first page</span>
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only">Go to previous page</span>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only">Go to next page</span>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only">Go to last page</span>
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
