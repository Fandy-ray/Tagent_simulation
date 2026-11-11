import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '@/lib/api/settings'
import { QUERY_KEYS } from '@/lib/api/query-client'

// 新版只读（见 lib/api/settings.ts）
export function useSettings() {
  return useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => settingsApi.get(),
  })
}
