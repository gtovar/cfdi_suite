import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnFiltersState,
  type FilterFn,
  type OnChangeFn,
  type SortingState,
} from '@tanstack/react-table';
import { useEffect, useMemo, useState } from 'react';
import type { CFDIIngresoRow, CFDIPagoRow } from '../../cfdi/public';
import type { ExtractColumn, ExtractGridController, ExtractMode } from '../../components/extract-workspace/types';

function getExtractCellValue(row: Record<string, string>, key: string) {
  return row[key] ?? '';
}

function compareValues(leftValue: string, rightValue: string) {
  const leftNumber = Number(leftValue);
  const rightNumber = Number(rightValue);
  const bothNumeric = !Number.isNaN(leftNumber) && !Number.isNaN(rightNumber) && leftValue !== '' && rightValue !== '';

  if (bothNumeric) {
    return leftNumber - rightNumber;
  }

  return leftValue.localeCompare(rightValue, 'es', { numeric: true, sensitivity: 'base' });
}

function asRecord(row: CFDIIngresoRow | CFDIPagoRow): Record<string, string> {
  return row as unknown as Record<string, string>;
}

function resolveStateUpdate<T>(nextValue: T | ((current: T) => T), current: T) {
  return typeof nextValue === 'function' ? (nextValue as (value: T) => T)(current) : nextValue;
}

export function useExtractGridState(params: {
  activeDatasetType: ExtractMode;
  ingresoRows: CFDIIngresoRow[];
  pagoRows: CFDIPagoRow[];
  extractColumns: readonly ExtractColumn[];
}) {
  const { activeDatasetType, ingresoRows, pagoRows, extractColumns } = params;
  const [extractSearchTerm, setExtractSearchTerm] = useState('');
  const [extractColumnFilterKey, setExtractColumnFilterKey] = useState<string>('all');
  const [extractPage, setExtractPageState] = useState(1);
  const [extractPageSize, setExtractPageSizeState] = useState(100);
  const [sorting, setSortingState] = useState<SortingState>([{ id: 'descripcion', desc: false }]);
  const [columnFilters, setColumnFiltersState] = useState<ColumnFiltersState>([]);
  const [hiddenIngresoColumns, setHiddenIngresoColumns] = useState<string[]>([]);
  const [hiddenPagoColumns, setHiddenPagoColumns] = useState<string[]>([]);
  const [ingresoColumnOrder, setIngresoColumnOrder] = useState<string[]>([]);
  const [pagoColumnOrder, setPagoColumnOrder] = useState<string[]>([]);
  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});

  const activeExtractBaseRows = useMemo(
    () => (activeDatasetType === 'ingresos' ? ingresoRows : pagoRows),
    [activeDatasetType, ingresoRows, pagoRows],
  );
  const activeExtractRows = useMemo(
    () => activeExtractBaseRows.map((row) => asRecord(row)),
    [activeExtractBaseRows],
  );
  const activeHiddenColumns = activeDatasetType === 'ingresos' ? hiddenIngresoColumns : hiddenPagoColumns;
  const activeStoredColumnOrder = activeDatasetType === 'ingresos' ? ingresoColumnOrder : pagoColumnOrder;
  const defaultColumnOrder = useMemo(() => extractColumns.map((column) => column.key), [extractColumns]);
  const columnOrder = useMemo(() => {
    if (activeStoredColumnOrder.length === 0) return defaultColumnOrder;

    const known = activeStoredColumnOrder.filter((key) => defaultColumnOrder.includes(key));
    const missing = defaultColumnOrder.filter((key) => !known.includes(key));
    return [...known, ...missing];
  }, [activeStoredColumnOrder, defaultColumnOrder]);
  const columnVisibility = useMemo(
    () => Object.fromEntries(extractColumns.map((column) => [column.key, !activeHiddenColumns.includes(column.key)])),
    [activeHiddenColumns, extractColumns],
  );

  const globalFilterFn = useMemo<FilterFn<Record<string, string>>>(
    () => (row, _columnId, filterValue) => {
      const search = String(filterValue ?? '').trim().toLowerCase();
      if (!search) return true;

      if (extractColumnFilterKey === 'all') {
        return Object.values(row.original).some((value) => String(value).toLowerCase().includes(search));
      }

      return getExtractCellValue(row.original, extractColumnFilterKey).toLowerCase().includes(search);
    },
    [extractColumnFilterKey],
  );

  const table = useReactTable<Record<string, string>>({
    data: activeExtractRows,
    columns: extractColumns.map((column) => ({
      id: column.key,
      accessorFn: (row: Record<string, string>) => getExtractCellValue(row, column.key),
      header: column.label,
      cell: (info) => String(info.getValue() ?? ''),
      filterFn: 'includesString',
      sortingFn: (left, right, columnId) =>
        compareValues(
          String(left.getValue(columnId) ?? '').toLowerCase(),
          String(right.getValue(columnId) ?? '').toLowerCase(),
        ),
      enableResizing: true,
      enableSorting: true,
    })),
    state: {
      globalFilter: extractSearchTerm,
      sorting,
      columnFilters,
      pagination: {
        pageIndex: Math.max(0, extractPage - 1),
        pageSize: extractPageSize,
      },
      columnVisibility,
      columnOrder,
      rowSelection,
    },
    enableMultiSort: true,
    enableRowSelection: true,
    columnResizeMode: 'onChange',
    globalFilterFn,
    onSortingChange: ((updater) => {
      setSortingState((current) => resolveStateUpdate(updater, current));
      setExtractPageState(1);
    }) as OnChangeFn<SortingState>,
    onColumnFiltersChange: ((updater) => {
      setColumnFiltersState((current) => resolveStateUpdate(updater, current));
      setExtractPageState(1);
    }) as OnChangeFn<ColumnFiltersState>,
    onRowSelectionChange: ((updater) => {
      setRowSelection((current) => resolveStateUpdate(updater, current));
    }) as OnChangeFn<Record<string, boolean>>,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    autoResetPageIndex: false,
  });

  const filteredExtractRows = table.getFilteredRowModel().rows.map((row) => row.original) as unknown as Array<CFDIIngresoRow | CFDIPagoRow>;
  const filteredExtractCount = table.getFilteredRowModel().rows.length;
  const totalExtractCount = activeExtractRows.length;
  const extractTotalPages = Math.max(1, table.getPageCount());
  const safeExtractPage = Math.min(extractPage, extractTotalPages);
  const extractPageStart = filteredExtractCount === 0 ? 0 : (safeExtractPage - 1) * extractPageSize;
  const selectedRowCount = table.getSelectedRowModel().rows.length;

  useEffect(() => {
    if (extractPage > extractTotalPages) {
      setExtractPageState(extractTotalPages);
    }
  }, [extractPage, extractTotalPages]);

  useEffect(() => {
    const nextDefaultSort = activeDatasetType === 'pagos' ? 'fechaPago' : 'descripcion';
    setSortingState((current) =>
      current.length > 0 ? current.filter((sort) => defaultColumnOrder.includes(sort.id)) : [{ id: nextDefaultSort, desc: false }],
    );
    setColumnFiltersState((current) => current.filter((filter) => defaultColumnOrder.includes(filter.id)));
  }, [activeDatasetType, defaultColumnOrder]);

  function setColumnOrderForActiveDataset(nextOrder: string[]) {
    if (activeDatasetType === 'ingresos') {
      setIngresoColumnOrder(nextOrder);
      return;
    }
    setPagoColumnOrder(nextOrder);
  }

  function resetForNewAnalysis(nextProfile: ExtractMode) {
    setExtractSearchTerm('');
    setExtractColumnFilterKey('all');
    setExtractPageState(1);
    setExtractPageSizeState(100);
    setSortingState([{ id: nextProfile === 'pagos' ? 'fechaPago' : 'descripcion', desc: false }]);
    setColumnFiltersState([]);
    setHiddenIngresoColumns([]);
    setHiddenPagoColumns([]);
    setIngresoColumnOrder([]);
    setPagoColumnOrder([]);
    setRowSelection({});
  }

  function resetGrid() {
    setExtractSearchTerm('');
    setExtractColumnFilterKey('all');
    setExtractPageState(1);
    setExtractPageSizeState(100);
    setSortingState([{ id: activeDatasetType === 'pagos' ? 'fechaPago' : 'descripcion', desc: false }]);
    setColumnFiltersState([]);
    setRowSelection({});
    if (activeDatasetType === 'ingresos') {
      setHiddenIngresoColumns([]);
      setIngresoColumnOrder([]);
    } else {
      setHiddenPagoColumns([]);
      setPagoColumnOrder([]);
    }
  }

  function toggleColumn(columnKey: string, hidden: boolean) {
    if (activeDatasetType === 'ingresos') {
      setHiddenIngresoColumns((current) => (hidden ? current.filter((key) => key !== columnKey) : [...current, columnKey]));
      return;
    }

    setHiddenPagoColumns((current) => (hidden ? current.filter((key) => key !== columnKey) : [...current, columnKey]));
  }

  function moveColumn(columnKey: string, direction: 'left' | 'right') {
    setColumnOrderForActiveDataset(
      (() => {
        const order = [...columnOrder];
        const currentIndex = order.indexOf(columnKey);
        if (currentIndex === -1) return order;
        const targetIndex = direction === 'left' ? currentIndex - 1 : currentIndex + 1;
        if (targetIndex < 0 || targetIndex >= order.length) return order;
        const [removed] = order.splice(currentIndex, 1);
        order.splice(targetIndex, 0, removed);
        return order;
      })(),
    );
  }

  function setColumnFilterValue(columnKey: string, value: string) {
    setColumnFiltersState((current) => {
      const next = current.filter((filter) => filter.id !== columnKey);
      if (!value.trim()) {
        return next;
      }
      return [...next, { id: columnKey, value }];
    });
    setExtractPageState(1);
  }

  function resetAll() {
    setExtractSearchTerm('');
    setExtractColumnFilterKey('all');
    setExtractPageState(1);
    setExtractPageSizeState(100);
    setSortingState([{ id: activeDatasetType === 'pagos' ? 'fechaPago' : 'descripcion', desc: false }]);
    setColumnFiltersState([]);
    setHiddenIngresoColumns([]);
    setHiddenPagoColumns([]);
    setIngresoColumnOrder([]);
    setPagoColumnOrder([]);
    setRowSelection({});
  }

  const extractGrid: ExtractGridController = {
    extractColumns,
    activeHiddenColumns,
    columnFilters,
    extractColumnFilterKey,
    extractSearchTerm,
    sorting,
    extractPageSize,
    filteredExtractCount,
    totalExtractCount,
    safeExtractPage,
    extractTotalPages,
    extractPageStart,
    selectedRowCount,
    table,
    setColumnFilterKey: (value) => {
      setExtractColumnFilterKey(value);
      setExtractPageState(1);
    },
    setColumnFilterValue,
    setSearchTerm: (value) => {
      setExtractSearchTerm(value);
      setExtractPageState(1);
    },
    setPageSize: (value) => {
      setExtractPageSizeState(value);
      setExtractPageState(1);
    },
    resetGrid,
    toggleColumn,
    moveColumn,
    toggleAllPageRowsSelected: () => table.toggleAllPageRowsSelected(!table.getIsAllPageRowsSelected()),
    goToPreviousPage: () => setExtractPageState((current) => Math.max(1, current - 1)),
    goToNextPage: () => setExtractPageState((current) => Math.min(extractTotalPages, current + 1)),
  };

  return {
    extractGrid,
    extractSearchTerm,
    filteredExtractRows,
    resetForNewAnalysis,
    resetAll,
  };
}
