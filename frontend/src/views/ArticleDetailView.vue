<template>
  <AppLayout>
    <div class="article-page" v-loading="loading">
      <template v-if="article">
        <el-button @click="$router.back()" text>← 返回</el-button>
        <h1>{{ article.title }}</h1>
        <div class="article-meta">
          <el-tag size="small">{{ article.category_name }}</el-tag>
          <span>作者: {{ article.author_name }}</span>
          <span>浏览: {{ article.view_count }}</span>
          <span>更新: {{ new Date(article.updated_at).toLocaleDateString() }}</span>
        </div>
        <el-divider />
        <div class="article-content" style="white-space: pre-wrap; line-height: 1.8;">{{ article.content }}</div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import { kbApi, type Article } from '@/api/kb'

const route = useRoute()
const loading = ref(false)
const article = ref<Article | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await kbApi.getArticle(route.params.slug as string)
    article.value = data
  } finally { loading.value = false }
})
</script>

<style scoped>
.article-page { max-width: 800px; margin: 0 auto; }
.article-meta { display: flex; gap: 16px; color: #909399; font-size: 13px; margin-top: 8px; align-items: center; }
</style>
