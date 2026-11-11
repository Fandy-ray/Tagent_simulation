import apiClient from './client'
import { Transformation } from '@/lib/types/transformations'

// 新版只读：变换是后端内置的 6 个，变换管理页（增删改、试验场、默认提示词）已砍掉。
export const transformationsApi = {
  list: async () => {
    const response = await apiClient.get<Transformation[]>('/transformations')
    return response.data
  },
}
