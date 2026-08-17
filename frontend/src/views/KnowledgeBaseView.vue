<template>
  <AppLayout>
    <div class="kb-page">
      <div class="kb-header">
        <h2>知识库</h2>
        <el-input v-model="searchQuery" placeholder="搜索文章..." clearable @keyup.enter="handleSearch" style="width: 320px;">
          <template #append><el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button></template>
        </el-input>
      </div>

      <div v-if="searchResults" class="search-results">
        <h3>搜索结果 ({{ searchResults.length }})</h3>
        <el-card v-for="article in searchResults" :key="article.id" class="article-card" @click="$router.push(`/kb/${article.slug}`)">
          <h4>{{ article.title }}</h4>
          <el-tag size="small">{{ article.category_name }}</el-tag>
          <span class="meta">浏览 {{ article.view_count }}</span>
        </el-card>
        <el-button v-if="searchResults.length" text @click="searchResults = null" style="margin-top: 8px;">清除搜索</el-button>
      </div>

      <div v-else>
        <div class="category-grid">
          <el-col :span="6" v-for="cat in categories" :key="cat.id">
            <el-card class="category-card">
              <h4>{{ cat.name }}</h4>
              <p>{{ cat.article_count }} 篇文章</p>
            </el-card>
          </el-col>
        </div>
        <h3 style="margin-top: 24px;">最新文章</h3>
        <el-table :data="articles" stripe @row-click="(row: any) => $router.push(`/kb/${row.slug}`)" style="cursor: pointer;">
          <el-table-column prop="title" label="标题" min-width="300">
            <template #default="{ row }"><a style="color: #409eff;">{{ row.title }}</a></template>
          </el-table-column>
          <el-table-column prop="category_name" label="分类" width="120">
            <template #default="{ row }"><el-tag size="small" type="info">{{ row.category_name }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="view_count" label="浏览" width="80" />
          <el-table-column prop="updated_at" label="更新时间" width="160">
            <template #default="{ row }">{{ new Date(row.updated_at).toLocaleDateString() }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { kbApi, type Article, type ArticleCategory } from '@/api/kb'

const categories = ref<ArticleCategory[]>([])
const articles = ref<Article[]>([])
const searchQuery = ref('')
const searchResults = ref<Article[] | null>(null)

async function handleSearch() {
  if (!searchQuery.value.trim()) { searchResults.value = null; return }
  const { data } = await kbApi.search(searchQuery.value)
  searchResults.value = data
}

onMounted(async () => {
  const [catResp, artResp] = await Promise.all([kbApi.listCategories(), kbApi.listArticles()])
  categories.value = (catResp.data as any).results || catResp.data
  articles.value = (artResp.data as any).results || artResp.data
})
</script>

<style scoped>
.kb-page { max-width: 1200px; }
.kb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.category-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.category-card { cursor: pointer; }
.category-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.article-card { cursor: pointer; margin-bottom: 8px; }
.meta { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
