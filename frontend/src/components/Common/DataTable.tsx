import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { useEffect } from "react"

import {
  DataTablePagination,
  DEFAULT_PAGE_SIZE,
} from "@/components/Common/DataTablePagination"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

/**
 * Server-side paging, when the list is too long to hand over whole.
 *
 * Its absence is the default and keeps the client-side behaviour every existing
 * caller relies on: `data` is the entire list, the table slices it. When it is
 * present `data` is **one page**, the table stops slicing (`manualPagination`),
 * and the footer counts against `total` rather than `data.length` — otherwise a
 * 25-row page of a 500-key list reads "25 entries", which is the number the
 * pager exists to contradict.
 */
export interface DataTableServerPagination {
  pageIndex: number
  pageSize: number
  /** Total matching rows on the server, not the length of this page. */
  total: number
  onPageChange: (pageIndex: number) => void
  /**
   * Omit to hide "Rows per page". A size change is followed by
   * `onPageChange(0)`: the list starts over at its first page.
   */
  onPageSizeChange?: (pageSize: number) => void
}

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  /** Omit for client-side paging over the whole list. */
  serverPagination?: DataTableServerPagination
  /** Shown in place of "No results found." when the list is empty. */
  emptyState?: React.ReactNode
  /**
   * Stable identity per row. Defaults to the row's index, which is wrong for a
   * server-paged list: index 0 is a different entity on every page, so React
   * reuses the previous page's cells and any per-row state with them.
   */
  getRowId?: (row: TData) => string
}

export function DataTable<TData, TValue>({
  columns,
  data,
  serverPagination,
  emptyState,
  getRowId,
}: DataTableProps<TData, TValue>) {
  const manual = serverPagination !== undefined
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: getRowId ? (row) => getRowId(row) : undefined,
    // Both models are still installed in the manual case: the row model is what
    // renders, and `getPaginationRowModel` is a no-op once `manualPagination`
    // tells the table the slicing has already happened.
    getPaginationRowModel: getPaginationRowModel(),
    // The server-paging options are spread in only when they apply. The table
    // merges options over its defaults with a plain spread, so an explicit
    // `onPaginationChange: undefined` replaces the built-in state updater and
    // every pager button in the client-side case silently does nothing.
    ...(manual
      ? {
          manualPagination: true,
          pageCount: Math.max(
            1,
            Math.ceil(serverPagination.total / serverPagination.pageSize),
          ),
          state: {
            pagination: {
              pageIndex: serverPagination.pageIndex,
              pageSize: serverPagination.pageSize,
            },
          },
          onPaginationChange: (updater) => {
            const current = {
              pageIndex: serverPagination.pageIndex,
              pageSize: serverPagination.pageSize,
            }
            const next =
              typeof updater === "function" ? updater(current) : updater
            // A new size starts over at the first page. The table would keep
            // the top row in view instead, but the index it derives for that
            // is reported separately from the size, and a caller that applies
            // them one after the other lands somewhere depending on the order.
            if (next.pageSize !== current.pageSize) {
              serverPagination.onPageSizeChange?.(next.pageSize)
              serverPagination.onPageChange(0)
              return
            }
            if (next.pageIndex !== current.pageIndex) {
              serverPagination.onPageChange(next.pageIndex)
            }
          },
        }
      : {
          initialState: {
            pagination: { pageIndex: 0, pageSize: DEFAULT_PAGE_SIZE },
          },
        }),
  })
  const total = manual ? serverPagination.total : data.length

  // A server-paged list can shrink under the current page (its last row
  // deleted). Step back to the last page that still exists — the footer may
  // already be gone, which would leave "No results found." with no way back.
  const pageCount = table.getPageCount()
  const serverPageIndex = serverPagination?.pageIndex
  const onServerPageChange = serverPagination?.onPageChange
  useEffect(() => {
    if (
      serverPageIndex !== undefined &&
      serverPageIndex > 0 &&
      serverPageIndex >= pageCount
    ) {
      onServerPageChange?.(pageCount - 1)
    }
  }, [serverPageIndex, pageCount, onServerPageChange])

  return (
    <div className="flex flex-col gap-4">
      {/* The table scrolls inside its own container rather than pushing the
          page sideways: a column set that fits at 1440 can still overflow at
          1024, and a horizontally scrolling page moves the sidebar with it. */}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={columns.length}
                  className="h-32 text-center text-muted-foreground"
                >
                  {emptyState ?? "No results found."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <DataTablePagination
        table={table}
        total={total}
        showPageSize={
          !manual || serverPagination.onPageSizeChange !== undefined
        }
      />
    </div>
  )
}
