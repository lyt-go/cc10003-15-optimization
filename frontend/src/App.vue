<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">指标口径与分析实验平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向业务指标定义、口径管理、聚合查询、分群分析、A/B实验设计、分析方案管理与数据服务发布的数据分析工程平台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "指标口径", path: "/metric" }, { label: "聚合查询", path: "/queryboard" }, { label: "分群分析", path: "/segment" }, { label: "实验设计", path: "/abtest" }, { label: "分析方案", path: "/analysis" }, { label: "看板配置", path: "/dashboard" }, { label: "数据服务", path: "/delivery" }, { label: "漏斗分析", path: "/funnel" }, { label: "同期群分析", path: "/cohort" }, { label: "留存刷新", path: "/retention" }, { label: "归因模型", path: "/attribution" }, { label: "指标预警", path: "/alertconfig" }, { label: "报表调度", path: "/reportsch" }, { label: "维度属性", path: "/dimprop" }, { label: "多维下钻", path: "/datadrill" }, { label: "预测模型", path: "/forecast" }, { label: "标签管理", path: "/tagmgr" }, { label: "洞察推送", path: "/insight" }, { label: "数据验证", path: "/dataval" }]
</script>
