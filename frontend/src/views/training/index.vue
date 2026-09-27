<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>人员培训管理</h2>
        <p class="page-desc">维护培训记录，围绕培训编号、培训主题、培训对象、授课人员做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记培训记录</button>
        <button class="btn" type="button" @click="exportRows">导出人员培训清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section v-if="completion" class="completion-panel">
      <header class="completion-head">
        <h3>结班判定</h3>
        <p class="completion-condition">结班条件：{{ completion.condition.说明 }}</p>
      </header>
      <template v-if="completion.待结班数 > 0">
        <p class="completion-summary">
          待结班 {{ completion.待结班数 }} 人，达标 {{ completion.达标人数 }} 人，未达标 {{ completion.未达标人数 }} 人
        </p>
        <table v-if="completion.未达标名单.length" class="data-table">
          <thead>
            <tr>
              <th v-for="column in unqualifiedColumns" :key="column">{{ column }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in completion.未达标名单" :key="String(row.id)">
              <td v-for="column in unqualifiedColumns" :key="column">{{ row[column] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">待结班的培训对象均已达标，可逐条执行确认结班</p>
      </template>
      <p v-else class="empty-state">当前没有待结班的培训，暂无结班判定对象</p>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无人员培训数据，可先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条人员培训记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface CompletionSummary {
  condition: {
    及格成绩: number
    满分: number
    标准课时: number
    说明: string
  }
  待结班数: number
  达标人数: number
  未达标人数: number
  未达标名单: Row[]
}

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训对象", "授课人员", "培训课时", "考核成绩", "培训日期", "培训状态"]
const actions = ["开班登记", "确认结班", "取消培训"]
const unqualifiedColumns = ["培训编号", "培训主题", "培训对象", "培训课时", "考核成绩", "未达标原因"]
// 筛选框列名与后端查询参数的对应关系，保证筛选条件真正生效
const filterParamMap: Record<string, string> = { "培训编号": "keyword", "培训主题": "topic", "培训对象": "trainee" }

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const completion = ref<CompletionSummary | null>(null)

const stats = computed(() => [
  { label: '待结班培训', value: completion.value?.待结班数 ?? 0 },
  { label: '达标人数', value: completion.value?.达标人数 ?? 0 },
  { label: '未达标人数', value: completion.value?.未达标人数 ?? 0 },
])

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [field, param] of Object.entries(filterParamMap)) {
    const value = filters.value[field]?.trim()
    if (value) {
      params.set(param, value)
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '培训记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 结班被拦下时展示后端给出的具体原因；筛选条件保持不动，可直接重试
      throw new Error(payload?.message ?? `人员培训动作「${action}」未生效，请稍后重试`)
    }
    noticeMessage.value = payload.message ?? `培训记录已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员培训操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  try {
    // 列表与结班判定用同一份筛选条件同时刷新，保证页面上的人数与列表数据一致
    const [listResponse, completionResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/completion?${query}`),
    ])
    if (!listResponse.ok) {
      throw new Error('培训记录列表读取失败')
    }
    if (!completionResponse.ok) {
      throw new Error('结班判定汇总读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    completion.value = await completionResponse.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员培训列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.completion-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.completion-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.completion-head h3 {
  margin: 0;
  font-size: 14px;
}
.completion-condition {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.completion-summary {
  margin: 8px 0;
  font-size: 13px;
}
.notice-text {
  color: #067647;
}
</style>
