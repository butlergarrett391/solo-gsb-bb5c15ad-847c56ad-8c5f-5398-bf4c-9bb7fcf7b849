"""核心织纹逻辑的单元测试（不依赖 FastAPI）。"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weave import (  # noqa: E402
    DesignError,
    analyze_loom_fit,
    analyze_repeat_period,
    audit_floats,
    best_alignment,
    build_interlacing,
    reduce_draft,
    repeat_period_of_matrix,
    scan_balance_hotspots,
    search_repair_plans,
    suggest_tie_up_flips,
    threshold_profile,
    validate_design,
    _proper_divisors,
    _runs,
)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def assert_tiles(matrix, period, msg):
    """校验 period.unit 在经纬两方向取模平铺后逐点等于整幅矩阵。"""
    wp, wfp, unit = period.warp_period, period.weft_period, period.unit
    picks, ends = len(matrix), len(matrix[0])
    check(wp >= 1 and wfp >= 1, f"{msg}: periods positive")
    check(ends % wp == 0, f"{msg}: warp_period divides ends")
    check(picks % wfp == 0, f"{msg}: weft_period divides picks")
    check(len(unit) == wfp and all(len(r) == wp for r in unit),
          f"{msg}: unit is weft_period x warp_period")
    tiled = all(
        matrix[h][w] == unit[h % wfp][w % wp]
        for h in range(picks)
        for w in range(ends)
    )
    check(tiled, f"{msg}: unit tiles the full matrix seamlessly (mod wrap)")


def assert_reduced(threading, tie_up, treadling, msg):
    """约简草图的通用不变量：尺寸、等价类划分、编号顺序、绑综、逐点重建。"""
    matrix = build_interlacing(threading, tie_up, treadling)
    picks, ends = len(matrix), len(matrix[0])
    reduced = reduce_draft(threading, tie_up, treadling)
    check(reduced.shafts >= 1 and reduced.treadles >= 1,
          f"{msg}: reduced counts positive")
    check(reduced.shafts <= len(tie_up[0])
          and reduced.treadles <= len(tie_up),
          f"{msg}: reduced counts never exceed the original declaration")
    check(len(reduced.threading) == ends
          and len(reduced.treadling) == picks,
          f"{msg}: reduced threading/treadling keep yarn counts")
    check(len(reduced.tie_up) == reduced.treadles
          and all(len(r) == reduced.shafts for r in reduced.tie_up),
          f"{msg}: reduced tie_up is min_treadles x min_shafts")
    check(all(0 <= s < reduced.shafts for s in reduced.threading)
          and all(0 <= t < reduced.treadles for t in reduced.treadling),
          f"{msg}: reduced indices in range")

    # shaft_classes / treadle_classes 构成原纱线的一个划分
    flat_cols = [w for cls in reduced.shaft_classes for w in cls]
    flat_rows = [h for cls in reduced.treadle_classes for h in cls]
    check(sorted(flat_cols) == list(range(ends)) and len(flat_cols) == ends,
          f"{msg}: shaft classes partition warp ends")
    check(sorted(flat_rows) == list(range(picks)) and len(flat_rows) == picks,
          f"{msg}: treadle classes partition weft picks")

    # 等价类按首次出现顺序从 0 编号
    first_cols = [cls[0] for cls in reduced.shaft_classes]
    first_rows = [cls[0] for cls in reduced.treadle_classes]
    check(first_cols == sorted(first_cols),
          f"{msg}: shaft classes numbered by first appearance")
    check(first_rows == sorted(first_rows),
          f"{msg}: treadle classes numbered by first appearance")
    class_of_col = {w: i for i, cls in enumerate(reduced.shaft_classes)
                    for w in cls}
    check(reduced.threading == [class_of_col[w] for w in range(ends)],
          f"{msg}: reduced threading matches shaft classes")
    class_of_row = {h: i for i, cls in enumerate(reduced.treadle_classes)
                    for h in cls}
    check(reduced.treadling == [class_of_row[h] for h in range(picks)],
          f"{msg}: reduced treadling matches treadle classes")

    # 同类列（行）向量确实相同；不同类列（行）向量确实不同
    for cls in reduced.shaft_classes:
        for w in cls:
            check([matrix[h][w] for h in range(picks)]
                  == [matrix[h][cls[0]] for h in range(picks)],
                  f"{msg}: same shaft class means identical column vectors")
    for i, cls_a in enumerate(reduced.shaft_classes):
        for j in range(i):
            wa, wb = reduced.shaft_classes[i][0], reduced.shaft_classes[j][0]
            check(any(matrix[h][wa] != matrix[h][wb] for h in range(picks)),
                  f"{msg}: distinct shaft classes have distinct column vectors")
    for cls in reduced.treadle_classes:
        for h in cls:
            check(matrix[h] == matrix[cls[0]],
                  f"{msg}: same treadle class means identical row vectors")
    for i, cls_a in enumerate(reduced.treadle_classes):
        for j in range(i):
            ha, hb = reduced.treadle_classes[i][0], reduced.treadle_classes[j][0]
            check(any(matrix[ha][w] != matrix[hb][w] for w in range(ends)),
                  f"{msg}: distinct treadle classes have distinct row vectors")

    # 约简绑综与代表元交叉点一致；逐点重建与原矩阵完全相同
    for ti, cls_h in enumerate(reduced.treadle_classes):
        for si, cls_w in enumerate(reduced.shaft_classes):
            check(reduced.tie_up[ti][si] == matrix[cls_h[0]][cls_w[0]],
                  f"{msg}: reduced tie_up cell matches representative crossing")
    rebuilt = build_interlacing(
        reduced.threading, reduced.tie_up, reduced.treadling
    )
    check(rebuilt == matrix and reduced.interlacing == matrix,
          f"{msg}: pointwise reconstruction equals the original matrix")
    return reduced


def test_reduce_draft_redundant_shafts_and_treadles():
    # 3 综 3 踏的声明，但交织矩阵只有 2 种列向量、2 种行向量
    threading = [0, 1, 2]
    tie_up = [[1, 0, 1], [0, 1, 0], [1, 0, 1]]
    treadling = [0, 1, 2]
    # 矩阵：
    # 1 0 1   （列 0 与列 2 相同）
    # 0 1 0
    # 1 0 1   （行 0 与行 2 相同）
    matrix = build_interlacing(threading, tie_up, treadling)
    check(matrix == [[1, 0, 1], [0, 1, 0], [1, 0, 1]],
          "redundant fixture matrix as expected")
    reduced = assert_reduced(threading, tie_up, treadling,
                             "redundant 3x3 draft")
    check(reduced.shafts == 2 and reduced.treadles == 2,
          "two distinct column vectors and two distinct row vectors")
    # 首次出现顺序：列 0=(1,0,1)→0，列 1=(0,1,0)→1；行同理
    check(reduced.threading == [0, 1, 0],
          "reduced threading groups identical columns, first-appearance order")
    check(reduced.treadling == [0, 1, 0],
          "reduced treadling groups identical rows, first-appearance order")
    check(reduced.tie_up == [[1, 0], [0, 1]],
          "reduced tie_up is the canonical 2x2 plain-weave draft")
    check(reduced.shaft_classes == [[0, 2], [1]],
          "shaft classes list original warp columns")
    check(reduced.treadle_classes == [[0, 2], [1]],
          "treadle classes list original weft rows")


def test_reduce_draft_different_original_shafts_same_column():
    # 经纱穿在不同原综框上，但列向量恰好相同 → 必须归并
    threading = [0, 2]
    tie_up = [[1, 0, 1]]   # 踏板 0 同时提升原综框 0、2
    treadling = [0, 0]
    matrix = build_interlacing(threading, tie_up, treadling)
    check(matrix == [[1, 1], [1, 1]], "all-ones matrix fixture")
    reduced = assert_reduced(threading, tie_up, treadling,
                             "different shafts identical column vectors")
    check(reduced.shafts == 1 and reduced.treadles == 1,
          "identical columns merge even if they used different original shafts")
    check(reduced.threading == [0, 0] and reduced.treadling == [0, 0],
          "everything maps to reduced shaft/treadle 0")
    check(reduced.tie_up == [[1]], "single reduced shaft and treadle")


def test_reduce_draft_unused_shafts_dropped():
    # 声明 4 综 4 踏，但踏板 3 从未被踩、综框 3 从未被穿入
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0, 0, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1]]
    treadling = [0, 1, 0, 1]
    reduced = assert_reduced(threading, tie_up, treadling,
                             "unused shafts and treadles")
    check(reduced.shafts == 2 and reduced.treadles == 2,
          "unused declared shafts/treadles are dropped")
    check(reduced.tie_up == [[1, 0], [0, 1]], "reduced plain-weave tie_up")


def test_reduce_draft_all_distinct_kept():
    # 3x3 单位阵：每个列向量、行向量都不同，无法约简
    threading = [0, 1, 2]
    tie_up = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    treadling = [0, 1, 2]
    reduced = assert_reduced(threading, tie_up, treadling,
                             "identity matrix needs no reduction")
    check(reduced.shafts == 3 and reduced.treadles == 3,
          "identity matrix needs all 3 shafts and 3 treadles")
    check(reduced.threading == [0, 1, 2] and reduced.treadling == [0, 1, 2]
          and reduced.tie_up == tie_up,
          "identity draft is unchanged by reduction")


def test_loom_fit_fit_flags_and_reductions():
    threading = [0, 1, 2]
    tie_up = [[1, 0, 1], [0, 1, 0], [1, 0, 1]]
    treadling = [0, 1, 2]

    fit = analyze_loom_fit(threading, tie_up, treadling, 2, 2)
    check(fit.fits is True and fit.shafts_fit and fit.treadles_fit,
          "2x2 device fits the reduced 2x2 requirement")
    check(fit.original_shafts == 3 and fit.original_treadles == 3,
          "original declared counts retained")
    check(fit.min_shafts == 2 and fit.min_treadles == 2,
          "minimum counts are the distinct vector counts")
    check(fit.shafts_removed == 1 and fit.treadles_removed == 1,
          "one shaft and one treadle removed")
    check(abs(fit.shaft_reduction_ratio - 1 / 3) < 1e-12
          and abs(fit.treadle_reduction_ratio - 1 / 3) < 1e-12,
          "reduction ratios relative to the original design")

    fit = analyze_loom_fit(threading, tie_up, treadling, 1, 2)
    check(fit.fits is False and fit.shafts_fit is False
          and fit.treadles_fit is True,
          "fits false when only shafts exceed the limit")
    fit = analyze_loom_fit(threading, tie_up, treadling, 2, 1)
    check(fit.fits is False and fit.shafts_fit is True
          and fit.treadles_fit is False,
          "fits false when only treadles exceed the limit")
    fit = analyze_loom_fit(threading, tie_up, treadling, 64, 64)
    check(fit.fits is True, "limit 64 always fits small designs")


def test_loom_fit_validation():
    threading, tie_up, treadling = [0, 1], [[1, 0], [0, 1]], [0, 1]
    for bad in (0, 65, -1, True, 1.5, "2"):
        try:
            analyze_loom_fit(threading, tie_up, treadling, bad, 2)
            raised = False
        except DesignError:
            raised = True
        check(raised, f"max_shafts={bad!r} rejected")
        try:
            analyze_loom_fit(threading, tie_up, treadling, 2, bad)
            raised = False
        except DesignError:
            raised = True
        check(raised, f"max_treadles={bad!r} rejected")


def test_reduce_draft_random_properties():
    rng = random.Random(20260922)
    for _ in range(200):
        shafts = rng.randint(1, 5)
        treadles = rng.randint(1, 5)
        tie_up = [[rng.randint(0, 1) for _ in range(shafts)]
                  for _ in range(treadles)]
        ends = rng.randint(1, 10)
        picks = rng.randint(1, 10)
        threading = [rng.randrange(shafts) for _ in range(ends)]
        treadling = [rng.randrange(treadles) for _ in range(picks)]
        matrix = build_interlacing(threading, tie_up, treadling)
        reduced = reduce_draft(threading, tie_up, treadling)
        # 最少综框数 = 不同列向量数（用集合独立核算）
        distinct_cols = len({
            tuple(matrix[h][w] for h in range(picks)) for w in range(ends)
        })
        distinct_rows = len({tuple(matrix[h]) for h in range(picks)})
        check(reduced.shafts == distinct_cols,
              "random: min_shafts equals distinct column vector count")
        check(reduced.treadles == distinct_rows,
              "random: min_treadles equals distinct row vector count")
        check(build_interlacing(
            reduced.threading, reduced.tie_up, reduced.treadling
        ) == matrix, "random: reconstructed matrix matches pointwise")



def test_interlacing():
    # 平纹：2 综 2 踏
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    m = build_interlacing(threading, tie_up, treadling)
    check(m == [[1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1]], "plain weave interlacing")


def test_warp_and_weft_floats():
    # 第 0 根经纱连续 3 纬浮起；第 0 纬纬纱连续浮过 3 根经纱
    threading = [0, 0, 0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 0, 1]
    # 矩阵:
    # 1 1 1
    # 1 1 1
    # 1 1 1
    # 0 0 0
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    warp = [x for x in v if x.direction == "warp"]
    weft = [x for x in v if x.direction == "weft"]
    check(len(warp) == 3 and all(x.length == 3 and x.start == 0 for x in warp),
          "warp floats of length 3 on all 3 ends")
    check(len(weft) == 1 and weft[0].yarn_index == 3 and weft[0].length == 3,
          "weft float of length 3 on pick 3")
    check(all(x.yarn_index in (0, 1, 2) for x in warp), "warp yarn indices")


def test_cyclic_merge():
    # 列: 1 1 0 0 1 1 -> 非循环两段(0,2),(4,2)；循环合并为 (4,4)
    check(_runs([1, 1, 0, 0, 1, 1], 1, False) == [(0, 2), (4, 2)],
          "non-cyclic runs")
    check(_runs([1, 1, 0, 0, 1, 1], 1, True) == [(4, 4)],
          "cyclic merge across boundary")
    # 全 1 列：只有一段，不自我合并
    check(_runs([1, 1, 1], 1, True) == [(0, 3)],
          "all-float line stays a single run")
    # 首尾不相接时不合并
    check(_runs([1, 0, 0, 1, 0], 1, True) == [(0, 1), (3, 1)],
          "no merge when boundary not both target")


def test_cyclic_audit_end_to_end():
    # 2/2 斜纹 4x4 循环，max_float=2：循环合并后每根经纱浮长恰为 2，不超限
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1] if False else [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(v == [], "2/2 twill cyclic: no float exceeds 2")
    # 非循环时边界处浮长仍 <= 2，也不超限
    _, v2 = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v2 == [], "2/2 twill non-cyclic: no float exceeds 2")
    # max_float=1 时循环与非循环都应报出浮长 2
    _, v3 = audit_floats(threading, tie_up, treadling, max_float=1, cyclic=True)
    check(len(v3) > 0 and all(x.length == 2 for x in v3),
          "2/2 twill with max_float=1 flags length-2 floats")


def test_cyclic_wrap_violation():
    # 构造跨边界合并后才超限的情形：列 1 1 0 1 1，max_float=2
    # 非循环：两段长度 2、2，不超限；循环：合并为长度 4，超限
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    _, v_off = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v_off == [], "wrap-around float not flagged when cyclic=False")
    _, v_on = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(len(v_on) == 1 and v_on[0].direction == "warp"
          and v_on[0].yarn_index == 0 and v_on[0].start == 3 and v_on[0].length == 4,
          "wrap-around float merged to length 4 starting at 3")


def test_repeat_period_plain_weave():
    # 平纹 4x4：交织矩阵 [[1,0,1,0],[0,1,0,1],...]，经纬周期都是 2，
    # 单元 2x2，是严格二维重复
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    period = analyze_repeat_period(threading, tie_up, treadling, 2)
    matrix = build_interlacing(threading, tie_up, treadling)
    check(period.warp_period == 2 and period.weft_period == 2,
          "plain weave: both periods are 2")
    check(period.unit == [[1, 0], [0, 1]], "plain weave: 2x2 unit")
    check(period.strict_2d_repeat is True, "plain weave: strict 2D repeat")
    assert_tiles(matrix, period, "plain weave")


def test_repeat_period_full_size_when_prime():
    # 3x3 满幅随机（尺寸为素数且无重复）：不存在小于整幅的周期，
    # 返回完整尺寸，unit 即整幅矩阵，strict_2d_repeat=False
    matrix = [
        [1, 0, 1],
        [0, 1, 1],
        [1, 1, 0],
    ]
    period = repeat_period_of_matrix(matrix)
    check(period.warp_period == 3 and period.weft_period == 3,
          "prime 3x3 matrix: no period smaller than full size")
    check(period.unit == matrix, "prime 3x3 matrix: unit is the full matrix")
    check(period.strict_2d_repeat is False,
          "prime 3x3 matrix: not strict 2D repeat")


def test_repeat_period_one_axis_only():
    # 仅经向重复、纬向不重复：列 [A B A B]，但两行不同
    # 1 0 1 0
    # 1 1 1 1
    # 经向周期 2（<4），纬向周期 2（=行数），不是严格二维重复
    matrix = [
        [1, 0, 1, 0],
        [1, 1, 1, 1],
    ]
    period = repeat_period_of_matrix(matrix)
    check(period.warp_period == 2, "one-axis: warp period 2")
    check(period.weft_period == 2, "one-axis: weft period full size 2")
    check(period.unit == [[1, 0], [1, 1]], "one-axis: unit is 2x2 (full height)")
    check(period.strict_2d_repeat is False,
          "one-axis: not strict 2D repeat (weft has no smaller period)")
    assert_tiles(matrix, period, "one-axis")


def test_repeat_period_based_on_matrix_not_threading():
    # 关键：周期必须基于交织矩阵，而非分别检查 threading/treadling。
    # 3 踏 3 综，仅踩踏板 0、1；tie_up 的第 0、2 列在这两行上相同
    # （穿综 0 与 2 的经纱交织表现一致），尽管穿综索引本身不同。
    # threading = [0,1,2,1]（作为序列最小周期 4，无 2-周期，因为 0!=2），
    # treadling = [0,1,0,1]（周期 2）。交织矩阵中穿综 0 与 2 的列相同，
    # 因此矩阵经向周期为 2。
    threading = [0, 1, 2, 1]
    tie_up = [[1, 0, 1], [0, 1, 0], [0, 0, 1]]
    treadling = [0, 1, 0, 1]
    period = analyze_repeat_period(threading, tie_up, treadling, 4)
    matrix = build_interlacing(threading, tie_up, treadling)
    # threading 序列本身没有 2-周期（threading[0]=0 != threading[2]=2）
    check(any(threading[w] != threading[w % 2] for w in range(4)),
          "threading sequence alone has no 2-period")
    check(period.warp_period == 2,
          "matrix warp period 2 despite threading sequence period 4")
    check(period.weft_period == 2, "matrix weft period 2")
    check(period.unit == [[1, 0], [0, 1]], "matrix-derived 2x2 unit")
    check(period.strict_2d_repeat is True, "matrix-derived strict 2D repeat")
    assert_tiles(matrix, period, "matrix-based")


def test_repeat_period_cyclic_boundary():
    # 循环设计的边界：单列、treadling [0,0,1] 重复两次（6 纬）。
    # 列为 1 1 0 1 1 0，周期 3 整除 6；取模回绕比较必须正确跨越首尾边界，
    # 不能因为末段(1,1)接首段(1,1)看似相连而误判为更小周期（2 不整除 6）。
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0, 1]
    # 该设计按 cyclic=true 审计
    matrix, _ = audit_floats(threading, tie_up, treadling, 2, cyclic=True)
    period = analyze_repeat_period(threading, tie_up, treadling, 2)
    check(period.warp_period == 1, "single-column: warp period 1")
    check(period.weft_period == 3, "cyclic boundary: weft period 3 (not 2)")
    check(period.unit == [[1], [1], [0]], "cyclic boundary: 3x1 unit")
    check(period.strict_2d_repeat is False,
          "cyclic boundary single column: not strict 2D repeat")
    assert_tiles(matrix, period, "cyclic boundary")

    # 直接对跨边界平铺的矩阵验证回绕：4 列模式在边界处也必须对齐
    wrap_matrix = [
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
    ]
    wp = repeat_period_of_matrix(wrap_matrix)
    check(wp.warp_period == 2 and wp.weft_period == 2,
          "wrap matrix aligned across both boundaries")
    assert_tiles(wrap_matrix, wp, "wrap matrix")


def test_repeat_period_constant_and_single_cell():
    # 全 1 矩阵 6x4：经纬周期都为 1
    all_ones = [[1] * 4 for _ in range(6)]
    period = repeat_period_of_matrix(all_ones)
    check(period.warp_period == 1 and period.weft_period == 1
          and period.unit == [[1]], "constant matrix: 1x1 unit")
    check(period.strict_2d_repeat is True, "constant 6x4: strict 2D repeat")
    assert_tiles(all_ones, period, "constant")

    # 1x1 单元即整幅，不是严格二维重复
    single = [[0]]
    p1 = repeat_period_of_matrix(single)
    check(p1.warp_period == 1 and p1.weft_period == 1 and p1.unit == [[0]],
          "single cell: periods 1")
    check(p1.strict_2d_repeat is False, "single cell: not strict 2D repeat")


def test_repeat_period_properties_random():
    # 随机交织矩阵：周期整除尺寸、单元无缝平铺、且没有更小的整除周期
    # （用朴素因子枚举交叉验证最小性）。
    rng = random.Random(20260921)
    check(_proper_divisors(12) == [1, 2, 3, 4, 6], "proper divisors helper")
    for picks in range(1, 9):
        for ends in range(1, 9):
            matrix = [[rng.randint(0, 1) for _ in range(ends)] for _ in range(picks)]
            period = repeat_period_of_matrix(matrix)
            assert_tiles(matrix, period, f"random {picks}x{ends}")

            for d in _proper_divisors(ends):
                if d >= period.warp_period:
                    break
                has_smaller = all(
                    matrix[h][w] == matrix[h][w % d]
                    for h in range(picks) for w in range(ends)
                )
                check(not has_smaller,
                      f"{picks}x{ends}: no warp divisor {d} smaller than "
                      f"{period.warp_period}")
            for d in _proper_divisors(picks):
                if d >= period.weft_period:
                    break
                has_smaller = all(
                    matrix[h][w] == matrix[h % d][w]
                    for h in range(picks) for w in range(ends)
                )
                check(not has_smaller,
                      f"{picks}x{ends}: no weft divisor {d} smaller than "
                      f"{period.weft_period}")
            expected_strict = period.warp_period < ends and period.weft_period < picks
            check(period.strict_2d_repeat == expected_strict,
                  f"{picks}x{ends}: strict_2d_repeat flag correct")


def test_tie_up_suggestions_basic():
    # 列 1 1 0 1 1 循环合并为长度 4 的经向浮长（max_float=2），共 1 条违规
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, True)
    # 仅 flip tie_up[0][0] -> 0 可消除违规；受影响点 = 踩踏板 0 的 4 纬 × 1 经
    check(len(suggestions) == 1, "exactly one improving flip")
    s = suggestions[0]
    check(s.treadle == 0 and s.shaft == 0 and s.new_value == 0,
          "flip tie_up[0][0] to 0")
    check(s.remaining_violations == 0, "no violations remain after flip")
    check(s.affected_points == 4, "4 interlacing points affected")
    # 原设计不被修改
    check(tie_up == [[1], [0]], "original tie_up unchanged")


def test_tie_up_suggestions_ordering():
    # 3 根经纱各浮 3 纬 + 末纬纬浮 3 经，共 4 条违规；多个单步翻转可改善
    threading = [0, 1, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, False)
    got = [(s.treadle, s.shaft, s.remaining_violations, s.affected_points)
           for s in suggestions]
    # 按 (剩余违规数, 受影响点数, 踏板索引, 综框索引) 升序
    check(got == [(0, 1, 2, 6), (1, 0, 3, 1), (1, 1, 3, 2), (0, 0, 3, 3)],
          "suggestions sorted by remaining, affected, treadle, shaft")
    check(all(s.remaining_violations < 4 for s in suggestions),
          "all candidates strictly reduce violations")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_tie_up_suggestions_no_improvement():
    # 平纹无违规：违规数为 0，不存在严格更少的翻转，返回空列表
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    check(suggest_tie_up_flips(threading, tie_up, treadling, 2, False) == [],
          "empty list when no flip improves")


def test_repair_plans_two_flips_needed():
    # 单列 6 纬全 1，cyclic 下整列一段长度 6，max_float=2：1 条经向违规。
    # 每个踏板各踩 1 纬，单次翻转只产生 1 个 0，仍有 1 条违规（长度 5）；
    # 循环上间隔恰为 3 的两次翻转把 1-段切成三段各长 2，违规清零。
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    _, base_v = audit_floats(threading, tie_up, treadling, 2, True)
    check(len(base_v) == 1, "baseline has exactly one violation")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=1)
    check(plans == [], "no improving plan within 1 flip")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2)
    # 循环 6 点上两个 0 间隔恰为 3 时三段各长 2：恰 3 个方案
    check(len(plans) == 3, f"3 two-flip plans, got {len(plans)}")
    seq0 = [(s.treadle, s.shaft) for s in plans[0].steps]
    check(seq0 == [(0, 0), (3, 0)], "lexicographically smallest sequence first")
    check([(s.treadle, s.shaft) for s in plans[1].steps] == [(1, 0), (4, 0)]
          and [(s.treadle, s.shaft) for s in plans[2].steps] == [(2, 0), (5, 0)],
          "remaining plans in lexicographic order")
    for p in plans:
        check(p.changes == 2 and p.final_violations == 0,
              "every plan uses 2 flips and clears violations")
        check(p.changed_points == 2, "2 interlacing points changed")
        check(len(p.steps) == 2 and p.steps[0].step == 1 and p.steps[1].step == 2,
              "steps are numbered 1..2")
        check(p.steps[0].old_value == 1 and p.steps[0].new_value == 0
              and p.steps[1].old_value == 1 and p.steps[1].new_value == 0,
              "flips 1 -> 0 with correct old/new values")
        check(p.steps[0].violations_after == 1,
              "intermediate state may keep violations unchanged")
        check(p.violations == [], "final violation list empty")
        check(sum(x for row in p.interlacing for x in row) == 4,
              "final matrix has exactly two zeros")
    check(tie_up == [[1], [1], [1], [1], [1], [1]],
          "original tie_up unchanged")


def test_repair_plans_state_dedup():
    # 同一绑综终态可由不同翻转序列到达：按状态去重，只保留字典序最小序列。
    # 2 踏 2 综，单列单纬时仅被踩踏板所提升的综框影响矩阵；构造多步搜索，
    # 验证终态去重（无重复终态）且原设计不被修改。
    threading = [0, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    plans = search_repair_plans(threading, tie_up, treadling, 2, False,
                                max_changes=3, limit=50)
    finals = []
    for p in plans:
        check(p.final_violations < 4, "plan strictly improves over baseline")
        # 同一单元在一条序列内不重复出现
        coords = [(s.treadle, s.shaft) for s in p.steps]
        check(len(coords) == len(set(coords)),
              "no cell flipped twice within one sequence")
        finals.append(tuple(tuple(row) for row in p.interlacing))
    check(len(finals) == len(set(finals)),
          "equivalent final states deduplicated")
    # 排序键：最终违规数、改动数、变化点数、序列字典序
    keys = [
        (p.final_violations, p.changes, p.changed_points,
         tuple((s.treadle, s.shaft) for s in p.steps))
        for p in plans
    ]
    check(keys == sorted(keys), "plans sorted by the declared key")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_repair_plans_limit_and_validation():
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2, limit=2)
    check(len(plans) == 2, "limit caps the number of plans")
    for bad in (0, 4):
        try:
            search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=bad)
            raise AssertionError(f"max_changes={bad} should be rejected")
        except DesignError:
            pass
    try:
        search_repair_plans(threading, tie_up, treadling, 2, True, limit=0)
        raise AssertionError("limit=0 should be rejected")
    except DesignError:
        pass
    print("  ok: repair plan parameter validation")


def test_best_alignment_shift_recovery():
    # b 为 a 沿纬向循环移 2 行、经向循环移 1 列：b[h][w] = a[(h+2)%3][(w+1)%3]
    # 对齐约定 aligned[h][w] = b[(h+ro)%H][(w+co)%W]，故最佳偏移为 (1, 2)
    a = [[1, 0, 1], [0, 1, 1], [1, 0, 0]]
    b = [[a[(h + 2) % 3][(w + 1) % 3] for w in range(3)] for h in range(3)]
    result = best_alignment(a, b)
    check(result.weft_offset == 1 and result.warp_offset == 2,
          "shifted copy: best offset recovers the cyclic shift")
    check(result.mismatch_count == 0 and result.mismatch_ratio == 0.0,
          "shifted copy: zero mismatches")
    check(result.aligned == a, "shifted copy: aligned matrix equals first matrix")
    check(result.mismatches == [], "shifted copy: no mismatch points")
    check(result.row_mismatches == [0, 0, 0]
          and result.col_mismatches == [0, 0, 0],
          "shifted copy: zero row/col summaries")
    check(a == [[1, 0, 1], [0, 1, 1], [1, 0, 0]]
          and b == [[0, 0, 1], [0, 1, 1], [1, 1, 0]],
          "input matrices unchanged")


def test_best_alignment_mismatch_details():
    # 仅 (2, 2) 单元不同：最佳对齐为零偏移，恰 1 处错位
    a = [[1, 0, 1], [0, 1, 1], [1, 1, 0]]
    c = [[1, 0, 1], [0, 1, 1], [1, 1, 1]]
    result = best_alignment(a, c)
    check(result.weft_offset == 0 and result.warp_offset == 0,
          "single-cell diff: zero offset")
    check(result.mismatch_count == 1, "single-cell diff: one mismatch")
    check(abs(result.mismatch_ratio - 1 / 9) < 1e-12,
          "single-cell diff: ratio 1/9")
    check(len(result.mismatches) == 1, "single-cell diff: one mismatch point")
    m = result.mismatches[0]
    check((m.row, m.col, m.design_value, m.other_value) == (2, 2, 0, 1),
          "single-cell diff: mismatch coordinate and values")
    check(result.row_mismatches == [0, 0, 1]
          and result.col_mismatches == [0, 0, 1],
          "single-cell diff: row/col summaries")
    check(result.aligned == c, "single-cell diff: aligned is unshifted second matrix")


def test_best_alignment_tie_break():
    # 行全同：偏移 (0,1) 与 (1,1) 同为 0 错位，按行偏移升序取 (0,1)
    a = [[1, 0], [1, 0]]
    b = [[0, 1], [0, 1]]
    result = best_alignment(a, b)
    check((result.weft_offset, result.warp_offset) == (0, 1),
          "row tie broken by smaller weft offset")
    check(result.mismatch_count == 0, "row tie: zero mismatches")
    # 单行：偏移 1 与 3 同为 0 错位，按列偏移升序取 1
    a1 = [[1, 0, 1, 0]]
    b1 = [[0, 1, 0, 1]]
    r1 = best_alignment(a1, b1)
    check((r1.weft_offset, r1.warp_offset) == (0, 1),
          "column tie broken by smaller warp offset")
    # 全同常量矩阵：所有偏移平局，取 (0, 0)
    r2 = best_alignment([[1, 1], [1, 1]], [[1, 1], [1, 1]])
    check((r2.weft_offset, r2.warp_offset) == (0, 0)
          and r2.mismatch_count == 0,
          "constant matrices: offset (0, 0)")


def test_best_alignment_dimension_mismatch():
    for a, b in (
        ([[1, 0], [0, 1]], [[1, 0, 1], [0, 1, 0]]),   # 列数不同
        ([[1, 0], [0, 1]], [[1, 0]]),                 # 行数不同
        ([[1]], []),                                  # 空矩阵
    ):
        try:
            best_alignment(a, b)
            raise AssertionError(f"{a} vs {b} should be rejected")
        except DesignError:
            pass
    print("  ok: dimension mismatch raises DesignError")


def test_threshold_profile_cyclic_wrap():
    # 单列 1 1 0 1 1，cyclic 合并为长度 4 的经向浮长：
    # 阈值 1..3 各 1 条经向违规，阈值 4 起零违规
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    profile = threshold_profile(threading, tie_up, treadling, True, 4)
    check(profile.max_float_limit == 4, "profile covers thresholds 1..4")
    check([p.max_float for p in profile.points] == [1, 2, 3, 4],
          "profile thresholds ascend 1..limit")
    check([(p.warp_violations, p.weft_violations, p.total_violations)
           for p in profile.points] == [(1, 0, 1), (1, 0, 1), (1, 0, 1), (0, 0, 0)],
          "cyclic wrap float cleared at threshold 4")
    check(profile.min_zero_violation_threshold == 4,
          "min zero-violation threshold is 4")
    # 上限内达不到零违规时为 None
    short = threshold_profile(threading, tie_up, treadling, True, 2)
    check(short.min_zero_violation_threshold is None
          and all(p.total_violations == 1 for p in short.points),
          "no zero-violation threshold within limit -> None")
    # 非循环语义下同一设计为两段长度 2 的浮长：阈值 1 有 2 条违规，阈值 2 清零
    plain = threshold_profile(threading, tie_up, treadling, False, 3)
    check(plain.min_zero_violation_threshold == 2
          and [p.total_violations for p in plain.points] == [2, 0, 0],
          "non-cyclic semantics preserved per threshold")


def test_threshold_profile_weft_direction():
    # 第 0 纬纬纱连续浮过 3 根经纱：阈值 1、2 各 1 条纬向违规，阈值 3 清零
    threading = [0, 0, 0]
    tie_up = [[0], [1]]
    treadling = [0, 1]
    profile = threshold_profile(threading, tie_up, treadling, False, 3)
    check([(p.warp_violations, p.weft_violations) for p in profile.points]
          == [(0, 1), (0, 1), (0, 0)],
          "weft-only float reported per threshold")
    check(profile.min_zero_violation_threshold == 3,
          "weft float cleared at threshold 3")


def test_threshold_profile_matches_audit_and_validation():
    # 随机设计：每档总数必须与同参数 audit_floats 的违规数一致，且单调不增
    rng = random.Random(20260922)
    for _ in range(30):
        shafts = rng.randint(1, 4)
        treadles = rng.randint(1, 4)
        threading = [rng.randrange(shafts) for _ in range(rng.randint(1, 8))]
        treadling = [rng.randrange(treadles) for _ in range(rng.randint(1, 8))]
        tie_up = [[rng.randint(0, 1) for _ in range(shafts)]
                  for _ in range(treadles)]
        cyclic = rng.random() < 0.5
        profile = threshold_profile(threading, tie_up, treadling, cyclic, 6)
        totals = []
        for point in profile.points:
            _, violations = audit_floats(
                threading, tie_up, treadling, point.max_float, cyclic
            )
            warp = sum(1 for v in violations if v.direction == "warp")
            check(point.total_violations == len(violations)
                  and point.warp_violations == warp
                  and point.weft_violations == len(violations) - warp,
                  "profile point matches full audit at the same threshold")
            totals.append(point.total_violations)
        check(totals == sorted(totals, reverse=True),
              "violation counts are non-increasing in threshold")
        if profile.min_zero_violation_threshold is not None:
            t = profile.min_zero_violation_threshold
            check(totals[t - 1] == 0 and (t == 1 or totals[t - 2] > 0),
                  "min zero-violation threshold is the first zero point")

    # 参数校验：非整数 / 越界的上限一律拒绝
    for bad in (0, 65, -1, True, 2.5, "3"):
        try:
            threshold_profile([0], [[1]], [0], False, bad)
            raise AssertionError(f"max_float_limit={bad!r} should be rejected")
        except DesignError:
            pass
    print("  ok: threshold profile parameter validation")


def test_balance_hotspots_non_cyclic():
    # 4x4 分块矩阵：
    # 1 1 0 0 / 1 1 0 0 / 0 0 1 1 / 0 0 1 1
    threading = [0, 0, 1, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 0, 1, 1]
    scan = scan_balance_hotspots(
        threading, tie_up, treadling, False, 2, 2, 0.25, 0.75
    )
    check(scan.windows_scanned == 9, "non-cyclic scans only contained windows")
    coords = [(h.row, h.col) for h in scan.hotspots]
    check(coords == [(0, 0), (0, 2), (2, 0), (2, 2)],
          "non-cyclic hotspots sorted by top-left coordinate")
    check([h.warp_ratio for h in scan.hotspots] == [1.0, 0.0, 0.0, 1.0],
          "non-cyclic hotspot ratios")
    check(all(h.deviation == 0.25 for h in scan.hotspots),
          "non-cyclic deviations from the nearest threshold")
    check(scan.worst_hotspot is scan.hotspots[0],
          "worst hotspot: tie broken by earliest scan order")

    # 阈值含边界：占比 0 / 1 在 [0, 1] 内不超界
    scan = scan_balance_hotspots(
        threading, tie_up, treadling, False, 2, 2, 0.0, 1.0
    )
    check(scan.hotspots == [] and scan.worst_hotspot is None,
          "inclusive thresholds: no hotspots, worst is None")

    # 窗口大于矩阵：非循环无窗可扫
    scan = scan_balance_hotspots(
        threading, tie_up, treadling, False, 5, 5, 0.25, 0.75
    )
    check(scan.windows_scanned == 0 and scan.hotspots == []
          and scan.worst_hotspot is None,
          "non-cyclic window larger than matrix scans nothing")


def test_balance_hotspots_cyclic_wrap():
    # 3x3 上三角矩阵：1 1 1 / 0 1 0 / 0 0 1
    threading = [0, 1, 2]
    tie_up = [[1, 1, 1], [0, 1, 0], [0, 0, 1]]
    treadling = [0, 1, 2]
    scan = scan_balance_hotspots(
        threading, tie_up, treadling, True, 2, 2, 0.3, 0.7
    )
    check(scan.windows_scanned == 9, "cyclic scans one window per cell")
    coords = [(h.row, h.col) for h in scan.hotspots]
    check(coords == [(0, 0), (0, 1), (1, 0), (1, 2), (2, 1), (2, 2)],
          "cyclic hotspots include wrap-around windows")
    check([h.warp_ratio for h in scan.hotspots]
          == [0.75, 0.75, 0.25, 0.25, 0.75, 0.75],
          "cyclic wrap-around window ratios")

    # 循环设计窗口超过矩阵尺寸 -> DesignError
    for rows, cols in ((4, 2), (2, 4), (4, 4)):
        try:
            scan_balance_hotspots(
                threading, tie_up, treadling, True, rows, cols, 0.0, 1.0
            )
            raise AssertionError(
                f"cyclic window {rows}x{cols} should be rejected"
            )
        except DesignError:
            pass
    print("  ok: cyclic window larger than matrix is rejected")


def test_balance_hotspots_random_against_brute_force():
    # 随机设计：与逐窗暴力求和对比，占比与扫描数必须一致
    rng = random.Random(20260922)
    for _ in range(30):
        shafts = rng.randint(1, 4)
        treadles = rng.randint(1, 4)
        threading = [rng.randrange(shafts) for _ in range(rng.randint(1, 8))]
        treadling = [rng.randrange(treadles) for _ in range(rng.randint(1, 8))]
        tie_up = [[rng.randint(0, 1) for _ in range(shafts)]
                  for _ in range(treadles)]
        cyclic = rng.random() < 0.5
        matrix = build_interlacing(threading, tie_up, treadling)
        picks, ends = len(matrix), len(matrix[0])
        wr = rng.randint(1, picks if cyclic else picks + 2)
        wc = rng.randint(1, ends if cyclic else ends + 2)
        lo = rng.random()
        hi = lo + rng.random() * (1.0 - lo)
        scan = scan_balance_hotspots(
            threading, tie_up, treadling, cyclic, wr, wc, lo, hi
        )

        if cyclic:
            origins = [(r, c) for r in range(picks) for c in range(ends)]
        else:
            origins = [(r, c)
                       for r in range(max(picks - wr + 1, 0))
                       for c in range(max(ends - wc + 1, 0))]
        check(scan.windows_scanned == len(origins),
              "scanned window count matches brute force origins")

        expected = []
        for r, c in origins:
            ones = sum(
                matrix[(r + i) % picks][(c + j) % ends]
                for i in range(wr) for j in range(wc)
            )
            ratio = ones / (wr * wc)
            if ratio < lo or ratio > hi:
                expected.append((r, c, ratio))
        got = [(h.row, h.col, h.warp_ratio) for h in scan.hotspots]
        check(len(got) == len(expected)
              and all(g == e for g, e in zip(got, expected)),
              "hotspot coordinates and ratios match brute force")
        for h in scan.hotspots:
            nearest = lo if h.warp_ratio < lo else hi
            check(abs(h.deviation - abs(h.warp_ratio - nearest)) < 1e-12,
                  "deviation is the distance to the nearest threshold")
        if expected:
            worst_dev = max(
                min(abs(ratio - lo), abs(ratio - hi))
                for _, _, ratio in expected
            )
            check(scan.worst_hotspot is not None
                  and abs(scan.worst_hotspot.deviation - worst_dev) < 1e-12,
                  "worst hotspot has the maximal deviation")
        else:
            check(scan.worst_hotspot is None,
                  "no hotspots -> worst is None")
    print("  ok: balance hotspots match brute force on random designs")


def test_balance_hotspots_validation():
    base = ([0], [[1]], [0])
    bad_calls = [
        (0, 2, 0.0, 1.0), (65, 2, 0.0, 1.0), (2, 0, 0.0, 1.0),
        (2, 65, 0.0, 1.0), (True, 2, 0.0, 1.0), (2.5, 2, 0.0, 1.0),
        (2, 2, -0.1, 1.0), (2, 2, 0.0, 1.1), (2, 2, 0.75, 0.25),
        (2, 2, True, 1.0), (2, 2, 0.0, "1"),
    ]
    for wr, wc, lo, hi in bad_calls:
        try:
            scan_balance_hotspots(*base, False, wr, wc, lo, hi)
            raise AssertionError(
                f"window=({wr},{wc}) thresholds=({lo},{hi}) should be rejected"
            )
        except DesignError:
            pass
    print("  ok: balance hotspots parameter validation")


def test_validation():
    ok_cases = []
    # 维度不一致：绑综矩阵不是矩形
    try:
        validate_design([0], [[1, 0], [1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 穿综索引越界
    try:
        validate_design([0, 2], [[1, 0], [0, 1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 踏综索引越界
    try:
        validate_design([0], [[1], [0]], [2], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 绑综取值非 0/1
    try:
        validate_design([0], [[2]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 空输入
    try:
        validate_design([], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 负索引
    try:
        validate_design([-1], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    check(all(ok_cases), "invalid designs are rejected")


if __name__ == "__main__":
    test_interlacing()
    test_warp_and_weft_floats()
    test_reduce_draft_redundant_shafts_and_treadles()
    test_reduce_draft_different_original_shafts_same_column()
    test_reduce_draft_unused_shafts_dropped()
    test_reduce_draft_all_distinct_kept()
    test_loom_fit_fit_flags_and_reductions()
    test_loom_fit_validation()
    test_reduce_draft_random_properties()
    test_cyclic_merge()
    test_cyclic_audit_end_to_end()
    test_cyclic_wrap_violation()
    test_repeat_period_plain_weave()
    test_repeat_period_full_size_when_prime()
    test_repeat_period_one_axis_only()
    test_repeat_period_based_on_matrix_not_threading()
    test_repeat_period_cyclic_boundary()
    test_repeat_period_constant_and_single_cell()
    test_repeat_period_properties_random()
    test_tie_up_suggestions_basic()
    test_tie_up_suggestions_ordering()
    test_tie_up_suggestions_no_improvement()
    test_repair_plans_two_flips_needed()
    test_repair_plans_state_dedup()
    test_repair_plans_limit_and_validation()
    test_best_alignment_shift_recovery()
    test_best_alignment_mismatch_details()
    test_best_alignment_tie_break()
    test_best_alignment_dimension_mismatch()
    test_threshold_profile_cyclic_wrap()
    test_threshold_profile_weft_direction()
    test_threshold_profile_matches_audit_and_validation()
    test_balance_hotspots_non_cyclic()
    test_balance_hotspots_cyclic_wrap()
    test_balance_hotspots_random_against_brute_force()
    test_balance_hotspots_validation()
    test_validation()
    print("all tests passed")
