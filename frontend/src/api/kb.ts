import request from './request'

export interface Article {
  id: string
  title: string
  slug: string
  content?: string
  category: string
  category_name: string
  tags: string
  is_published: boolean
  view_count: number
  author_name: string
  created_at: string
  updated_at: string
}

export interface ArticleCategory {
  id: string
  name: string
  order: number
  article_count: number
}

export const kbApi = {
  listArticles() {
    return request.get('/kb/articles/')
  },
  getArticle(slug: string) {
    return request.get<Article>(`/kb/articles/${slug}/`)
  },
  search(q: string) {
    return request.get<Article[]>('/kb/articles/search/', { params: { q } })
  },
  listCategories() {
    return request.get<ArticleCategory[]>('/kb/categories/')
  },
  createArticle(data: Partial<Article>) {
    return request.post('/kb/articles/manage/', data)
  },
  updateArticle(id: string, data: Partial<Article>) {
    return request.put(`/kb/articles/manage/${id}/`, data)
  },
  deleteArticle(id: string) {
    return request.delete(`/kb/articles/manage/${id}/`)
  },
}
