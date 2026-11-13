"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import metric as router_metric
from app.routers import queryboard as router_queryboard
from app.routers import segment as router_segment
from app.routers import abtest as router_abtest
from app.routers import analysis as router_analysis
from app.routers import dashboard as router_dashboard
from app.routers import delivery as router_delivery
from app.routers import funnel as router_funnel
from app.routers import cohort as router_cohort
from app.routers import retention as router_retention
from app.routers import attribution as router_attribution
from app.routers import alertconfig as router_alertconfig
from app.routers import reportsch as router_reportsch
from app.routers import dimprop as router_dimprop
from app.routers import datadrill as router_datadrill
from app.routers import forecast as router_forecast
from app.routers import tagmgr as router_tagmgr
from app.routers import insight as router_insight
from app.routers import dataval as router_dataval

ROUTERS = [router_metric, router_queryboard, router_segment, router_abtest, router_analysis, router_dashboard, router_delivery, router_funnel, router_cohort, router_retention, router_attribution, router_alertconfig, router_reportsch, router_dimprop, router_datadrill, router_forecast, router_tagmgr, router_insight, router_dataval]
