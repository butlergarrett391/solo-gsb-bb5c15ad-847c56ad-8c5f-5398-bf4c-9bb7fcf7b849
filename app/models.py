"""请求 / 响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DesignIn(BaseModel):
    """一份待审计的机织纹样设计。"""

    name: str | None = Field(default=None, description="设计名称（可选）")
    cyclic: bool = Field(
        default=False,
        description="纹样是否循环；为 true 时合并矩阵首尾跨边界的连续浮长段",
    )
    max_float: int = Field(..., ge=1, description="允许的最大浮长，超过即判违规")
    threading: list[int] = Field(
        ..., description="经纱穿综映射：threading[w] 为第 w 根经纱所穿综框的索引"
    )
    tie_up: list[list[int]] = Field(
        ...,
        description="绑综矩阵：tie_up[t][s] ∈ {0,1}，踏板 t 是否提升综框 s；"
        "行数 = 踏板数，列数 = 综框数",
    )
    treadling: list[int] = Field(
        ..., description="逐纬踏综序列：treadling[h] 为第 h 纬踩下的踏板索引"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "2/2 twill, 8x8 repeat",
                    "cyclic": True,
                    "max_float": 2,
                    "threading": [0, 1, 2, 3, 0, 1, 2, 3],
                    "tie_up": [
                        [1, 1, 0, 0],
                        [0, 1, 1, 0],
                        [0, 0, 1, 1],
                        [1, 0, 0, 1],
                    ],
                    "treadling": [0, 1, 2, 3, 0, 1, 2, 3],
                }
            ]
        }
    }


class Violation(BaseModel):
    direction: Literal["warp", "weft"] = Field(
        ..., description="warp=经向浮长（经纱连续浮于纬上），weft=纬向浮长"
    )
    yarn_index: int = Field(..., description="纱线索引：经纱列号或纬纱行号")
    start: int = Field(
        ..., description="连续段起点；循环合并段取尾部段的起点（跨边界延伸）"
    )
    length: int = Field(..., description="连续浮长")


class AuditOut(BaseModel):
    exceeds: bool = Field(..., description="是否存在超过 max_float 的浮长")
    interlacing: list[list[int]] = Field(
        ..., description="经纬交织矩阵，1=经纱在上，0=纬纱在上"
    )
    violations: list[Violation]


class DesignOut(BaseModel):
    id: int
    name: str | None
    cyclic: bool
    max_float: int
    shafts: int
    treadles: int
    warp_ends: int
    weft_picks: int
    threading: list[int]
    tie_up: list[list[int]]
    treadling: list[int]
    created_at: str
    audit: AuditOut


class DesignSummary(BaseModel):
    id: int
    name: str | None
    cyclic: bool
    max_float: int
    shafts: int
    treadles: int
    warp_ends: int
    weft_picks: int
    exceeds: bool
    created_at: str


class TieUpSuggestionOut(BaseModel):
    """单步绑综修复建议：翻转一个 tie_up 单元后违规总数严格减少的候选。"""

    treadle: int = Field(..., description="踏板索引（tie_up 行号）")
    shaft: int = Field(..., description="综框索引（tie_up 列号）")
    new_value: Literal[0, 1] = Field(..., description="该单元翻转后的新值")
    remaining_violations: int = Field(
        ..., description="翻转后按原 cyclic、max_float 重跑审计的剩余违规总数"
    )
    affected_points: int = Field(
        ..., description="受影响交织点数：翻转前后交织矩阵中取值变化的单元数"
    )


class RepairPlanStepOut(BaseModel):
    """修复方案中的一步绑综翻转。"""

    step: int = Field(..., description="第几步翻转（从 1 开始）")
    treadle: int = Field(..., description="踏板索引（tie_up 行号）")
    shaft: int = Field(..., description="综框索引（tie_up 列号）")
    old_value: Literal[0, 1] = Field(..., description="翻转前该单元的值")
    new_value: Literal[0, 1] = Field(..., description="翻转后该单元的值")
    violations_after: int = Field(
        ..., description="本次翻转后完整审计的违规总数（中间状态允许不下降）"
    )


class RepairPlanOut(BaseModel):
    """多步绑综修复方案：终态违规总数严格少于原设计。"""

    changes: int = Field(..., description="方案翻转次数（1～max_changes）")
    final_violations: int = Field(..., description="最终违规总数")
    changed_points: int = Field(
        ..., description="最终交织矩阵相对原矩阵取值变化的点数"
    )
    steps: list[RepairPlanStepOut] = Field(..., description="逐步翻转序列")
    violations: list[Violation] = Field(..., description="最终违规列表")
    interlacing: list[list[int]] = Field(
        ..., description="最终交织矩阵，1=经纱在上，0=纬纱在上"
    )


class RepeatPeriodOut(BaseModel):
    """交织矩阵的最小循环单元分析。"""

    warp_period: int = Field(
        ..., description="经向最小正周期（一个循环单元的列数/经纱数），整除经纱数"
    )
    weft_period: int = Field(
        ..., description="纬向最小正周期（一个循环单元的行数/纬纱数），整除纬纱数"
    )
    unit: list[list[int]] = Field(
        ...,
        description="最小循环单元矩阵（weft_period 行 × warp_period 列），"
        "1=经纱在上，0=纬纱在上；在经纬两方向重复平铺可无缝还原整幅交织矩阵",
    )
    strict_2d_repeat: bool = Field(
        ...,
        description="是否为严格二维重复：仅当 warp_period、weft_period 均严格小于"
        "整幅对应尺寸（单元在两个方向都至少平铺 2 次）时为 true",
    )


class ReducedDraftOut(BaseModel):
    """基于交织矩阵约简出的最简草图（threading/treadling/tie_up）。"""

    shafts: int = Field(
        ..., description="约简后综框数：交织矩阵中不同完整列向量的数量"
    )
    treadles: int = Field(
        ..., description="约简后踏板数：交织矩阵中不同完整行向量的数量"
    )
    threading: list[int] = Field(
        ...,
        description="约简穿综映射：threading[w] 为第 w 根经纱所属约简综框"
        "（完整列向量等价类，按首次出现顺序从 0 编号）",
    )
    treadling: list[int] = Field(
        ...,
        description="约简踏综序列：treadling[h] 为第 h 纬所属约简踏板"
        "（完整行向量等价类，按首次出现顺序从 0 编号）",
    )
    tie_up: list[list[int]] = Field(
        ...,
        description="约简绑综矩阵：treadles 行 × shafts 列，0/1；由约简"
        "threading/treadling 重建，逐点校验与原交织矩阵一致",
    )
    shaft_classes: list[list[int]] = Field(
        ...,
        description="每个约简综框包含的原经纱列号，按综框编号排列；"
        "类内编号按经纱首次出现顺序",
    )
    treadle_classes: list[list[int]] = Field(
        ...,
        description="每个约简踏板包含的原纬纱行号，按踏板编号排列；"
        "类内编号按纬纱首次出现顺序",
    )
    interlacing: list[list[int]] = Field(
        ...,
        description="由约简草图重建的交织矩阵（1=经纱在上，0=纬纱在上），"
        "已逐点校验与原设计交织矩阵完全一致",
    )


class LoomFitIn(BaseModel):
    """织机适配性（草图约简）请求：设备综框/踏板上限。"""

    max_shafts: int = Field(
        ..., ge=1, le=64, description="织机综框数上限，1～64"
    )
    max_treadles: int = Field(
        ..., ge=1, le=64, description="织机踏板数上限，1～64"
    )


class LoomFitOut(BaseModel):
    """交织矩阵相对设备综框/踏板上限的适配性与约简草图。"""

    design_id: int = Field(..., description="被分析的设计 ID")
    max_shafts: int = Field(..., description="请求给定的综框数上限")
    max_treadles: int = Field(..., description="请求给定的踏板数上限")
    original_shafts: int = Field(..., description="原设计声明的综框数")
    original_treadles: int = Field(..., description="原设计声明的踏板数")
    min_shafts: int = Field(
        ..., description="织出该交织矩阵所需的最少综框数（不同完整列向量数）"
    )
    min_treadles: int = Field(
        ..., description="织出该交织矩阵所需的最少踏板数（不同完整行向量数）"
    )
    fits: bool = Field(
        ...,
        description="是否适配：仅当 min_shafts ≤ max_shafts 且 "
        "min_treadles ≤ max_treadles 时为 true",
    )
    shafts_fit: bool = Field(
        ..., description="最少综框数是否不超过 max_shafts"
    )
    treadles_fit: bool = Field(
        ..., description="最少踏板数是否不超过 max_treadles"
    )
    shafts_removed: int = Field(
        ..., description="相对原设计约简掉的综框数：original_shafts - min_shafts"
    )
    treadles_removed: int = Field(
        ..., description="相对原设计约简掉的踏板数：original_treadles - min_treadles"
    )
    shaft_reduction_ratio: float = Field(
        ..., description="综框减少比例：shafts_removed / original_shafts，0～1"
    )
    treadle_reduction_ratio: float = Field(
        ..., description="踏板减少比例：treadles_removed / original_treadles，0～1"
    )
    reduced_draft: ReducedDraftOut = Field(
        ..., description="按交织矩阵等价类重建的约简草图"
    )


class ErrorOut(BaseModel):
    detail: str


class BalanceHotspotsIn(BaseModel):
    """局部交织均衡审计请求。"""

    window_rows: int = Field(
        ..., ge=1, le=64, description="窗口行数（纬向高度），1～64"
    )
    window_cols: int = Field(
        ..., ge=1, le=64, description="窗口列数（经向宽度），1～64"
    )
    warp_ratio_min: float = Field(
        ..., ge=0.0, le=1.0,
        description="窗口内 1（经纱在上）占比的允许下限（含），0～1",
    )
    warp_ratio_max: float = Field(
        ..., ge=0.0, le=1.0,
        description="窗口内 1（经纱在上）占比的允许上限（含），0～1",
    )

    @model_validator(mode="after")
    def _thresholds_ordered(self):
        if self.warp_ratio_min > self.warp_ratio_max:
            raise ValueError("warp_ratio_min must not exceed warp_ratio_max")
        return self


class BalanceHotspotOut(BaseModel):
    """一个超界窗口：左上角坐标、占比与偏离最近阈值的幅度。"""

    row: int = Field(..., description="窗口左上角纬纱行号")
    col: int = Field(..., description="窗口左上角经纱列号")
    warp_ratio: float = Field(..., description="窗口内 1（经纱在上）的占比")
    deviation: float = Field(..., description="占比偏离最近阈值的幅度")


class BalanceHotspotsOut(BaseModel):
    """局部交织均衡审计结果。"""

    design_id: int = Field(..., description="被审计的设计 ID")
    cyclic: bool = Field(..., description="审计沿用的设计循环声明")
    window_rows: int = Field(..., description="窗口行数（纬向高度）")
    window_cols: int = Field(..., description="窗口列数（经向宽度）")
    warp_ratio_min: float = Field(..., description="占比允许下限（含）")
    warp_ratio_max: float = Field(..., description="占比允许上限（含）")
    windows_scanned: int = Field(..., description="实际扫描的窗口总数")
    hotspots: list[BalanceHotspotOut] = Field(
        ..., description="超界窗口列表，按左上角行、列升序稳定排序"
    )
    worst_hotspot: BalanceHotspotOut | None = Field(
        ..., description="偏离最近阈值幅度最大的超界窗口；无超界时为 null"
    )


class ThresholdProfilePointOut(BaseModel):
    """单档阈值下完整经纬浮长审计的违规汇总。"""

    max_float: int = Field(..., description="本档允许的最大浮长阈值，超过即判违规")
    warp_violations: int = Field(..., description="该阈值下的经向浮长违规数")
    weft_violations: int = Field(..., description="该阈值下的纬向浮长违规数")
    total_violations: int = Field(
        ..., description="该阈值下的违规总数（经向 + 纬向）"
    )


class ThresholdProfileOut(BaseModel):
    """阈值敏感性分析：1..max_float_limit 逐档重跑完整浮长审计的结果。"""

    design_id: int = Field(..., description="被分析的设计 ID")
    cyclic: bool = Field(..., description="逐档审计沿用的设计循环声明")
    max_float: int = Field(..., description="设计入库时声明的最大浮长阈值")
    max_float_limit: int = Field(..., description="本次逐档审计的阈值上限")
    min_zero_violation_threshold: int | None = Field(
        ...,
        description="达到零违规的最小阈值；上限内无法达到零违规时为 null",
    )
    profile: list[ThresholdProfilePointOut] = Field(
        ..., description="逐档审计结果，按阈值 1..max_float_limit 升序"
    )


class DesignCompareIn(BaseModel):
    """设计对齐比对请求。"""

    other_design_id: int = Field(
        ..., ge=1, description="参与比对的另一份已入库设计 ID"
    )


class MismatchPointOut(BaseModel):
    """最佳对齐下一个不一致单元的坐标与双方取值。"""

    row: int = Field(..., description="错位单元所在纬纱行号")
    col: int = Field(..., description="错位单元所在经纱列号")
    design_value: int = Field(..., description="第一份设计交织矩阵在该单元的值")
    other_value: int = Field(..., description="第二份设计矩阵对齐后在该单元的值")


class DesignCompareOut(BaseModel):
    """两份设计交织矩阵的最佳循环对齐比对结果。"""

    design_id: int = Field(..., description="第一份（路径指定的）设计 ID")
    other_design_id: int = Field(..., description="第二份（被循环错位比对的）设计 ID")
    warp_ends: int = Field(..., description="两份设计共同的经纱数（矩阵列数）")
    weft_picks: int = Field(..., description="两份设计共同的纬纱数（矩阵行数）")
    weft_offset: int = Field(
        ..., description="第二份矩阵沿纬向（行）的最佳循环错位量"
    )
    warp_offset: int = Field(
        ..., description="第二份矩阵沿经向（列）的最佳循环错位量"
    )
    mismatch_count: int = Field(..., description="最佳对齐下不一致单元数")
    mismatch_ratio: float = Field(
        ..., description="不一致单元占比：mismatch_count / (weft_picks × warp_ends)"
    )
    mismatches: list[MismatchPointOut] = Field(
        ..., description="错位坐标列表，按行、列升序"
    )
    row_mismatches: list[int] = Field(
        ..., description="按行汇总：row_mismatches[h] 为第 h 纬的错位数"
    )
    col_mismatches: list[int] = Field(
        ..., description="按列汇总：col_mismatches[w] 为第 w 根经纱的错位数"
    )
    aligned: list[list[int]] = Field(
        ...,
        description="最佳对齐后的第二份交织矩阵（1=经纱在上，0=纬纱在上）："
        "aligned[h][w] = 原矩阵[(h + weft_offset) % 行数][(w + warp_offset) % 列数]",
    )
