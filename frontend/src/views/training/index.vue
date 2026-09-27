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

    <section class="panel" data-panel="completion">
      <h3 class="panel-title">结班判定</h3>
      <p class="criteria-banner">结班条件：{{ summary?.结班条件?.说明 ?? '读取中' }}</p>
      <p v-if="summary && summary.待结班数 === 0" class="empty-state">
        当前没有待结班的培训，进行中的培训班出现后会自动更新达标情况
      </p>
      <template v-else-if="summary">
        <p v-if="!summary.未达标名单.length" class="empty-state">待结班培训全部达标，可放心办理结班</p>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>培训编号</th>
              <th>培训主题</th>
              <th>培训对象</th>
              <th>培训课时</th>
              <th>考核成绩</th>
              <th>未达标原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in summary.未达标名单" :key="String(item.id)">
              <td>{{ item.培训编号 ?? '—' }}</td>
              <td>{{ item.培训主题 || '—' }}</td>
              <td>{{ item.培训对象 ?? '—' }}</td>
              <td>{{ item.培训课时 ?? '—' }}</td>
              <td>{{ item.考核成绩 ?? '—' }}</td>
              <td class="fail-text">{{ item.未达标原因 }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <ul v-if="summary && summary.数据质量提示.length" class="issue-list">
        <li v-for="issue in summary.数据质量提示" :key="`${issue.id}-${issue.问题}`">
          记录#{{ issue.id }}（{{ issue.培训编号 }}）：{{ issue.问题 }}
        </li>
      </ul>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>结班判定</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td :class="{ 'fail-text': isFailed(row) }">{{ judgementOf(row) }}</td>
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
          <td :colspan="columns.length + 2" class="empty-state">暂无人员培训数据，可先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条人员培训记录</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button v-if="lastFailed" class="link" type="button" @click="retryLastAction">重试</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FailedEntry = Row & { 未达标原因?: string }
type Summary = {
  结班条件: { 满分: number; 及格线: number; 要求课时: number; 说明: string }
  待结班数: number
  达标人数: number
  未达标人数: number
  达标名单: Row[]
  未达标名单: FailedEntry[]
  数据质量提示: Array<{ id: number; 培训编号: string; 问题: string }>
}

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训对象", "授课人员", "培训课时", "考核成绩", "培训日期", "培训状态"]
const actions = ["开班登记", "确认结班", "取消培训"]
const statuses = ["待开班", "进行中", "已结班", "已取消"]
const filterParamMap: Record<string, string> = { 培训编号: 'keyword', 培训主题: 'topic', 培训对象: 'target' }

const rows = ref<Row[]>([])
const total = ref(0)
const summary = ref<Summary | null>(null)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)
const lastFailed = ref<{ action: string; row: Row } | null>(null)

const stats = computed(() => [
  { label: '待结班培训', value: summary.value?.待结班数 ?? 0 },
  { label: '达标人数', value: summary.value?.达标人数 ?? 0 },
  { label: '未达标人数', value: summary.value?.未达标人数 ?? 0 },
])

const judgementById = computed(() => {
  const map = new Map<number, { passed: boolean; text: string }>()
  for (const item of summary.value?.达标名单 ?? []) {
    map.set(Number(item.id), { passed: true, text: '达标' })
  }
  for (const item of summary.value?.未达标名单 ?? []) {
    map.set(Number(item.id), { passed: false, text: `未达标：${item.未达标原因 ?? ''}` })
  }
  return map
})

function judgementOf(row: Row): string {
  return judgementById.value.get(Number(row.id))?.text ?? '—'
}

function isFailed(row: Row): boolean {
  return judgementById.value.get(Number(row.id))?.passed === false
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
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
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message ?? payload.detail ?? '人员培训动作未生效，请稍后重试')
    }
    lastFailed.value = null
    await reload()
  } catch (error) {
    lastFailed.value = { action, row }
    errorMessage.value = error instanceof Error ? error.message : '人员培训操作失败'
  }
}

async function retryLastAction() {
  if (lastFailed.value) {
    await runAction(lastFailed.value.action, lastFailed.value.row)
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [field, param] of Object.entries(filterParamMap)) {
    const value = (filters.value[field] ?? '').trim()
    if (value) {
      params.set(param, value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${params.toString()}`),
      request(`${ENDPOINT}/completion/summary`),
    ])
    if (!listResponse.ok) {
      throw new Error('培训记录列表读取失败')
    }
    if (!summaryResponse.ok) {
      throw new Error('结班判定汇总读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    summary.value = (await summaryResponse.json()) as Summary
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员培训列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.panel-title {
  margin: 0 0 8px;
  font-size: 14px;
}
.criteria-banner {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--brand);
}
.fail-text {
  color: #b42318;
}
.issue-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #b42318;
  font-size: 13px;
}
.filter-item select {
  min-width: 120px;
}
</style>
