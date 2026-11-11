import { useQuery } from '@tanstack/react-query'
import { modelsApi } from '@/lib/api/models'

// 新版只读（见 lib/api/models.ts）
export const MODEL_QUERY_KEYS = {
  models: ['models'] as const,
  defaults: ['models', 'defaults'] as const,
}

export function useModels() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.models,
    queryFn: () => modelsApi.list(),
  })
}

export function useModelDefaults() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.defaults,
    queryFn: () => modelsApi.getDefaults(),
  })
}
