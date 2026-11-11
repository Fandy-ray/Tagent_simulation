import apiClient from './client'

export interface EmbedContentRequest {
  item_id: string
  item_type: 'source' | 'note'
  async_processing?: boolean
}

export interface EmbedContentResponse {
  success: boolean
  message: string
  chunks_created?: number
  command_id?: string
}

export const embeddingApi = {
  embedContent: async (itemId: string, itemType: 'source' | 'note', asyncProcessing = false): Promise<EmbedContentResponse> => {
    const response = await apiClient.post<EmbedContentResponse>('/embed', {
      item_id: itemId,
      item_type: itemType,
      async_processing: asyncProcessing
    })
    return response.data
  }
}
