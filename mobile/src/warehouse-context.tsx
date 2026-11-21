import { createContext, useContext, type ReactNode } from 'react';
import { useWarehouse } from './warehouse';

const WarehouseContext = createContext<ReturnType<typeof useWarehouse> | null>(null);

export function WarehouseProvider({ children }: { children: ReactNode }) {
  const warehouse = useWarehouse();
  return <WarehouseContext.Provider value={warehouse}>{children}</WarehouseContext.Provider>;
}

export function useWarehouseContext() {
  const warehouse = useContext(WarehouseContext);
  if (!warehouse) throw new Error('WarehouseProvider is required');
  return warehouse;
}
