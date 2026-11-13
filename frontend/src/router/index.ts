import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
const Metric = () => import('@/views/metric/index.vue')
const Queryboard = () => import('@/views/queryboard/index.vue')
const Segment = () => import('@/views/segment/index.vue')
const Abtest = () => import('@/views/abtest/index.vue')
const Analysis = () => import('@/views/analysis/index.vue')
const Dashboard = () => import('@/views/dashboard/index.vue')
const Delivery = () => import('@/views/delivery/index.vue')
const Funnel = () => import('@/views/funnel/index.vue')
const Cohort = () => import('@/views/cohort/index.vue')
const Retention = () => import('@/views/retention/index.vue')
const Attribution = () => import('@/views/attribution/index.vue')
const Alertconfig = () => import('@/views/alertconfig/index.vue')
const Reportsch = () => import('@/views/reportsch/index.vue')
const Dimprop = () => import('@/views/dimprop/index.vue')
const Datadrill = () => import('@/views/datadrill/index.vue')
const Forecast = () => import('@/views/forecast/index.vue')
const Tagmgr = () => import('@/views/tagmgr/index.vue')
const Insight = () => import('@/views/insight/index.vue')
const Dataval = () => import('@/views/dataval/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/metric', name: 'metric', component: Metric },
    { path: '/queryboard', name: 'queryboard', component: Queryboard },
    { path: '/segment', name: 'segment', component: Segment },
    { path: '/abtest', name: 'abtest', component: Abtest },
    { path: '/analysis', name: 'analysis', component: Analysis },
    { path: '/dashboard', name: 'dashboard', component: Dashboard },
    { path: '/delivery', name: 'delivery', component: Delivery },
    { path: '/funnel', name: 'funnel', component: Funnel },
    { path: '/cohort', name: 'cohort', component: Cohort },
    { path: '/retention', name: 'retention', component: Retention },
    { path: '/attribution', name: 'attribution', component: Attribution },
    { path: '/alertconfig', name: 'alertconfig', component: Alertconfig },
    { path: '/reportsch', name: 'reportsch', component: Reportsch },
    { path: '/dimprop', name: 'dimprop', component: Dimprop },
    { path: '/datadrill', name: 'datadrill', component: Datadrill },
    { path: '/forecast', name: 'forecast', component: Forecast },
    { path: '/tagmgr', name: 'tagmgr', component: Tagmgr },
    { path: '/insight', name: 'insight', component: Insight },
    { path: '/dataval', name: 'dataval', component: Dataval },
  ],
})

export default router
