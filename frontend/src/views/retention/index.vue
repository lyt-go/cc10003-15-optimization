<template>
  <section class="page" data-module="retention">
    <header class="page-head">
      <div>
        <h2>漏斗留存增量刷新</h2>
        <p class="page-desc">
          漏斗与同期群联合入口：按漏斗版本、划分事件、观察周期和已覆盖群组计算待重算窗口，
          只处理新增、失效与待补窗口，其余留存结果沿用。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="!selected" @click="runRefresh(false)">
          增量刷新
        </button>
        <button class="btn" type="button" :disabled="!lastIdempotencyKey" @click="runRefresh(true)">
          重放上次刷新
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in planColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in plans" :key="row.plan_key" :class="{ 'row-active': row.plan_key === selectedKey }">
          <td>{{ row.plan_key }}</td>
          <td>{{ row['漏斗编号'] }} / {{ row['漏斗版本'] }}</td>
          <td>{{ row['划分事件'] }}</td>
          <td>{{ (row['观察周期列表'] || []).join(',') }}</td>
          <td>{{ row.coverage_version }}</td>
          <td>{{ watermarkText(row) }}</td>
          <td>{{ row['最后计算时间'] }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="selectPlan(row.plan_key)">窗口详情</button>
          </td>
        </tr>
        <tr v-if="!plans.length">
          <td :colspan="planColumns.length + 1" class="empty-state">暂无留存刷新计划</td>
        </tr>
      </tbody>
    </table>

    <section v-if="detail" class="detail-panel">
      <h3>
        窗口矩阵 · {{ detail.plan_key }}
        <span class="coverage-tag">覆盖版本 {{ detail.coverage_version }} · 建议策略 {{ detail['建议策略'] }}</span>
      </h3>
      <div class="class-summary">
        <span v-for="name in classNames" :key="name" class="class-chip" :data-class="name">
          {{ name }} {{ (detail['窗口分类'][name] || []).length }}
        </span>
      </div>
      <table class="data-table matrix-table">
        <thead>
          <tr>
            <th>群组批次</th>
            <th v-for="day in detail['观察周期列表']" :key="day">第 {{ day }} 天</th>
            <th>完成水位</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="batch in batches" :key="batch">
            <td>{{ batch }}</td>
            <td
              v-for="day in detail['观察周期列表']"
              :key="day"
              class="matrix-cell"
              :data-class="cellClass(batch, day)"
            >
              <span class="cell-class">{{ cellClass(batch, day) }}</span>
              <span class="cell-rate">{{ cellRate(batch, day) }}</span>
            </td>
            <td>第 {{ watermarkOf(batch) }} 天</td>
          </tr>
        </tbody>
      </table>
      <p class="panel-note">
        完成水位记录 window_day、cohort_batch、covered_members、failed_members 与 checkpoint_seq；
        越界成员单列展示，不计入留存率。
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th>群组批次</th><th>window_day</th><th>covered_members</th>
            <th>failed_members</th><th>checkpoint_seq</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="cp in detail['水位明细']" :key="cp.cohort_batch">
            <td>{{ cp.cohort_batch }}</td>
            <td>{{ cp.window_day }}</td>
            <td>{{ cp.covered_members }}</td>
            <td>{{ cp.failed_members }}</td>
            <td>{{ cp.checkpoint_seq }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="detail-panel">
      <h3>刷新审计</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>批次</th><th>策略</th><th>新增</th><th>失效</th><th>复用</th><th>待补</th>
            <th>重算</th><th>状态</th><th>覆盖版本</th><th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in audits" :key="run.run_id">
            <td>{{ run.run_id }}</td>
            <td>{{ run.strategy }}</td>
            <td>{{ run['新增'].length }}</td>
            <td>{{ run['失效'].length }}</td>
            <td>{{ run['复用'].length }}</td>
            <td>{{ run['待补'].length }}</td>
            <td>{{ run.succeeded }}</td>
            <td>{{ run.status }}</td>
            <td>{{ run.coverage_before }} → {{ run.coverage_after }}</td>
            <td>{{ run.created_at }}</td>
          </tr>
          <tr v-if="!audits.length">
            <td colspan="10" class="empty-state">暂无刷新审计记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ plans.length }} 个联合计划</span>
      <span v-if="message" class="ok-text">{{ message }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/retention'
const classNames = ['新增', '失效', '复用', '待补']
const planColumns = ['计划标识', '漏斗/版本', '划分事件', '观察周期', '覆盖版本', '完成水位', '最后计算时间']

const plans = ref<Row[]>([])
const audits = ref<Row[]>([])
const detail = ref<Row | null>(null)
const selectedKey = ref('')
const message = ref('')
const errorMessage = ref('')
const lastIdempotencyKey = ref('')

const selected = computed(() => selectedKey.value !== '')

const stats = computed(() => {
  const current = plans.value[0]
  const gapCount = detail.value ? (detail.value['窗口分类']['待补'] || []).length : 0
  const staleCount = detail.value ? (detail.value['窗口分类']['失效'] || []).length : 0
  return [
    { label: '联合计划', value: plans.value.length },
    { label: '当前覆盖版本', value: current ? current.coverage_version : '—' },
    { label: '待补窗口', value: gapCount },
    { label: '失效窗口', value: staleCount },
  ]
})

const batches = computed(() => {
  if (!detail.value) return []
  const set = new Set<string>()
  for (const row of detail.value['窗口明细'] || []) set.add(row.cohort_batch)
  for (const batch of detail.value['待算群组'] || []) set.add(batch)
  return Array.from(set).sort()
})

function watermarkText(row: Row) {
  const marks = row['完成水位'] || {}
  const parts = Object.entries(marks).map(([batch, day]) => `${batch}:第${day}天`)
  return parts.length ? parts.join('；') : '—'
}

function watermarkOf(batch: string) {
  const cp = (detail.value?.['水位明细'] || []).find((row: Row) => row.cohort_batch === batch)
  return cp ? cp.window_day : 0
}

function classMap(): Map<string, string> {
  const map = new Map<string, string>()
  if (!detail.value) return map
  for (const name of classNames) {
    for (const key of detail.value['窗口分类'][name] || []) map.set(key, name)
  }
  return map
}

function cellClass(batch: string, day: number) {
  return classMap().get(`${batch}#${day}`) ?? '新增'
}

function cellRate(batch: string, day: number) {
  const row = (detail.value?.['窗口明细'] || []).find(
    (item: Row) => item.cohort_batch === batch && item.window_day === day,
  )
  if (!row) return '—'
  if (row.status !== 'success') return `失败(转化 ${row.conversion_rate ?? '—'})`
  return `留存 ${row.retention_rate}`
}

async function selectPlan(planKey: string) {
  selectedKey.value = planKey
  await loadDetail()
}

async function runRefresh(replay: boolean) {
  if (!selectedKey.value) return
  message.value = ''
  errorMessage.value = ''
  const idempotencyKey = replay ? lastIdempotencyKey.value : `ui-${Date.now()}`
  try {
    const response = await request(`${ENDPOINT}/plans/${selectedKey.value}/refresh`, {
      method: 'POST',
      body: JSON.stringify({ values: { idempotency_key: idempotencyKey } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '增量刷新未生效')
    }
    lastIdempotencyKey.value = idempotencyKey
    message.value = payload.message
    await Promise.all([loadPlans(), loadDetail(), loadAudits()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '增量刷新失败'
  }
}

async function loadPlans() {
  const response = await request(`${ENDPOINT}/plans`)
  const payload = await response.json()
  plans.value = payload.items ?? []
  if (!selectedKey.value && plans.value.length) {
    selectedKey.value = plans.value[0].plan_key
    await loadDetail()
  }
}

async function loadDetail() {
  if (!selectedKey.value) return
  const response = await request(`${ENDPOINT}/plans/${selectedKey.value}`)
  detail.value = await response.json()
}

async function loadAudits() {
  const response = await request(`${ENDPOINT}/audits`)
  const payload = await response.json()
  audits.value = payload.items ?? []
}

onMounted(async () => {
  errorMessage.value = ''
  try {
    await Promise.all([loadPlans(), loadAudits()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '留存刷新数据读取失败'
  }
})
</script>

<style scoped>
.detail-panel { margin-top: 16px; }
.detail-panel h3 { font-size: 14px; margin: 0 0 8px; }
.coverage-tag { font-size: 12px; color: var(--muted); margin-left: 8px; }
.class-summary { display: flex; gap: 8px; margin-bottom: 8px; }
.class-chip { padding: 2px 10px; border-radius: 10px; font-size: 12px; border: 1px solid var(--border); }
.class-chip[data-class='新增'] { background: #e0f2fe; }
.class-chip[data-class='失效'] { background: #fee2e2; }
.class-chip[data-class='复用'] { background: #dcfce7; }
.class-chip[data-class='待补'] { background: #fef9c3; }
.matrix-cell { text-align: center; }
.matrix-cell .cell-class { display: block; font-size: 12px; }
.matrix-cell .cell-rate { font-size: 12px; color: var(--muted); }
.matrix-cell[data-class='新增'] { background: #e0f2fe; }
.matrix-cell[data-class='失效'] { background: #fee2e2; }
.matrix-cell[data-class='复用'] { background: #dcfce7; }
.matrix-cell[data-class='待补'] { background: #fef9c3; }
.panel-note { font-size: 12px; color: var(--muted); margin: 8px 0; }
.row-active td { background: #eff6ff; }
.ok-text { color: #15803d; }
</style>
