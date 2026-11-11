import { useQuery } from '@tanstack/react-query'
import { transformationsApi } from '@/lib/api/transformations'

// 新版只读（见 lib/api/transformations.ts）
export const TRANSFORMATION_QUERY_KEYS = {
  transformations: ['transformations'] as const,
}

export function useTransformations() {
  return useQuery({
    queryKey: TRANSFORMATION_QUERY_KEYS.transformations,
    queryFn: () => transformationsApi.list(),
  })
}
