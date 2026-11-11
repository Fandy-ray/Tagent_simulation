import apiClient from './client'
import { Model, ModelDefaults } from '@/lib/types/models'

// 新版只读：模型改由后端环境变量配置（ON_LLM_*、ON_EMBEDDING_*），
// 这里只给界面上的模型下拉框取清单和默认值；增删、发现、测试模型的接口都已砍掉。
export const modelsApi = {
  list: async () => {
    const response = await apiClient.get<Model[]>('/models')
    return response.data
  },

  getDefaults: async () => {
    const response = await apiClient.get<ModelDefaults>('/models/defaults')
    return response.data
  },
}
