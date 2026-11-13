"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None



class MetricEntry(BaseModel):
    """指标定义明细结构。"""

    field_0: str | None = None  # 指标编号
    field_1: str | None = None  # 指标名称
    field_2: str | None = None  # 计算公式
    field_3: str | None = None  # 统计粒度
    field_4: str | None = None  # 时间窗口
    field_5: str | None = None  # 筛选条件
    field_6: str | None = None  # 精度位数
    field_7: str | None = None  # 口径版本

class QueryboardEntry(BaseModel):
    """查询模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 指标名称
    field_2: str | None = None  # 维度字段
    field_3: str | None = None  # 度量字段
    field_4: str | None = None  # 排序规则
    field_5: str | None = None  # 分页上限
    field_6: str | None = None  # 缓存秒数
    field_7: str | None = None  # 数据源

class SegmentEntry(BaseModel):
    """人群分群明细结构。"""

    field_0: str | None = None  # 分群编号
    field_1: str | None = None  # 分群名称
    field_2: str | None = None  # 筛选规则
    field_3: str | None = None  # 最小规模
    field_4: str | None = None  # 最大规模
    field_5: str | None = None  # 刷新周期
    field_6: str | None = None  # 最近计算时间
    field_7: str | None = None  # 最终规模

class AbtestEntry(BaseModel):
    """实验方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 实验名称
    field_2: str | None = None  # 对照组定义
    field_3: str | None = None  # 实验组定义
    field_4: str | None = None  # 分流比例
    field_5: str | None = None  # 核心指标
    field_6: str | None = None  # 最小样本量
    field_7: str | None = None  # 预计周期

class AnalysisEntry(BaseModel):
    """分析方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 分析主题
    field_2: str | None = None  # 数据集范围
    field_3: str | None = None  # 分析方法
    field_4: str | None = None  # 对比基准
    field_5: str | None = None  # 显著性阈值
    field_6: str | None = None  # 输出图表类型
    field_7: str | None = None  # 调度周期

class DashboardEntry(BaseModel):
    """看板页面明细结构。"""

    field_0: str | None = None  # 看板编号
    field_1: str | None = None  # 看板名称
    field_2: str | None = None  # 包含指标
    field_3: str | None = None  # 布局模板
    field_4: str | None = None  # 刷新间隔
    field_5: str | None = None  # 可见范围
    field_6: str | None = None  # 所属业务线
    field_7: str | None = None  # 看板负责人

class DeliveryEntry(BaseModel):
    """服务版本明细结构。"""

    field_0: str | None = None  # 服务编号
    field_1: str | None = None  # 数据集名称
    field_2: str | None = None  # 查询参数定义
    field_3: str | None = None  # 返回字段
    field_4: str | None = None  # 速率限制
    field_5: str | None = None  # 分页最大条数
    field_6: str | None = None  # 版本号
    field_7: str | None = None  # 消费方应用

class FunnelEntry(BaseModel):
    """漏斗定义明细结构。"""

    field_0: str | None = None  # 漏斗编号
    field_1: str | None = None  # 漏斗名称
    field_2: str | None = None  # 步骤序列
    field_3: str | None = None  # 转化窗口天
    field_4: str | None = None  # 步骤名称列表
    field_5: str | None = None  # 事件定义
    field_6: str | None = None  # 关联指标
    field_7: str | None = None  # 最小样本量

class CohortEntry(BaseModel):
    """同期群定义明细结构。"""

    field_0: str | None = None  # 群组编号
    field_1: str | None = None  # 群组名称
    field_2: str | None = None  # 划分事件
    field_3: str | None = None  # 观察指标
    field_4: str | None = None  # 观察周期天
    field_5: str | None = None  # 群组粒度
    field_6: str | None = None  # 留存阈值
    field_7: str | None = None  # 最后计算时间

class RetentionPlanEntry(BaseModel):
    """留存刷新计划明细结构。"""

    field_0: str | None = None  # 计划标识
    field_1: str | None = None  # 漏斗编号
    field_2: str | None = None  # 漏斗版本
    field_3: str | None = None  # 群组编号
    field_4: str | None = None  # 划分事件
    field_5: str | None = None  # 观察周期列表
    field_6: str | None = None  # 覆盖版本
    field_7: str | None = None  # 最后计算时间

class AttributionEntry(BaseModel):
    """归因规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 归因类型
    field_2: str | None = None  # 回溯窗口天
    field_3: str | None = None  # 触点权重
    field_4: str | None = None  # 首次触点权重
    field_5: str | None = None  # 末次触点权重
    field_6: str | None = None  # 中间触点衰减
    field_7: str | None = None  # 关联渠道

class AlertconfigEntry(BaseModel):
    """预警规则明细结构。"""

    field_0: str | None = None  # 预警编号
    field_1: str | None = None  # 关联指标
    field_2: str | None = None  # 比较运算符
    field_3: str | None = None  # 阈值数值
    field_4: str | None = None  # 持续周期数
    field_5: str | None = None  # 预警级别
    field_6: str | None = None  # 通知接收人
    field_7: str | None = None  # 静默时段

class ReportschEntry(BaseModel):
    """报表任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 报表名称
    field_2: str | None = None  # 包含指标
    field_3: str | None = None  # 输出格式
    field_4: str | None = None  # 调度cron
    field_5: str | None = None  # 收件人列表
    field_6: str | None = None  # 数据日期偏移
    field_7: str | None = None  # 重试次数上限

class DimpropEntry(BaseModel):
    """维度属性明细结构。"""

    field_0: str | None = None  # 属性编号
    field_1: str | None = None  # 维度名称
    field_2: str | None = None  # 属性名称
    field_3: str | None = None  # 数据类型
    field_4: str | None = None  # 枚举值列表
    field_5: str | None = None  # 关联数据源
    field_6: str | None = None  # 更新频率
    field_7: str | None = None  # 最近更新时间

class DatadrillEntry(BaseModel):
    """下钻路径明细结构。"""

    field_0: str | None = None  # 路径编号
    field_1: str | None = None  # 起始维度
    field_2: str | None = None  # 下钻层级
    field_3: str | None = None  # 每层维度名
    field_4: str | None = None  # 每层度量
    field_5: str | None = None  # 路径深度
    field_6: str | None = None  # 默认展开层
    field_7: str | None = None  # 关联看板

class ForecastEntry(BaseModel):
    """预测方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 预测目标
    field_2: str | None = None  # 算法名称
    field_3: str | None = None  # 特征字段
    field_4: str | None = None  # 训练周期
    field_5: str | None = None  # 预测窗口天
    field_6: str | None = None  # 置信水平
    field_7: str | None = None  # 模型版本

class TagmgrEntry(BaseModel):
    """标签定义明细结构。"""

    field_0: str | None = None  # 标签编号
    field_1: str | None = None  # 标签名称
    field_2: str | None = None  # 标签分类
    field_3: str | None = None  # 计算逻辑
    field_4: str | None = None  # 值类型
    field_5: str | None = None  # 刷新周期
    field_6: str | None = None  # 覆盖对象数
    field_7: str | None = None  # 最近计算时间

class InsightEntry(BaseModel):
    """洞察报告明细结构。"""

    field_0: str | None = None  # 报告编号
    field_1: str | None = None  # 报告标题
    field_2: str | None = None  # 分析主题
    field_3: str | None = None  # 关键发现
    field_4: str | None = None  # 数据来源
    field_5: str | None = None  # 生成时间
    field_6: str | None = None  # 推送渠道
    field_7: str | None = None  # 推送状态

class DatavalEntry(BaseModel):
    """验证任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 验证数据集
    field_2: str | None = None  # 验证类型
    field_3: str | None = None  # 基准数据
    field_4: str | None = None  # 对比维度
    field_5: str | None = None  # 差异阈值
    field_6: str | None = None  # 验证周期
    field_7: str | None = None  # 最近验证结果
