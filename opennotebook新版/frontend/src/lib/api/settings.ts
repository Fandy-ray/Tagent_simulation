import apiClient from './client'
import { SettingsResponse } from '@/lib/types/api'

// 新版只读：设置页已砍掉，添加来源对话框只需要读「默认是否嵌入」。
export const settingsApi = {
  get: async () => {
    const response = await apiClient.get<SettingsResponse>('/settings')
    return response.data
  },
}
