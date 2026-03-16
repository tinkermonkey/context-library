import { Badge } from 'flowbite-react';
import { useHealth } from '../hooks/useHealth';

export function HealthIndicator() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading || isError) {
    return <Badge color="gray">Unknown</Badge>;
  }

  if (data?.sqlite_ok && data?.chromadb_ok) {
    return <Badge color="green">Healthy</Badge>;
  }

  if (data?.sqlite_ok !== data?.chromadb_ok) {
    return <Badge color="yellow">Degraded</Badge>;
  }

  return <Badge color="red">Unhealthy</Badge>;
}
