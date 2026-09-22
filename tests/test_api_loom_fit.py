"""POST /designs/{id}/loom-fit 的接口集成测试。

使用临时 SQLite 文件与 FastAPI TestClient，不依赖运行中的服务，也不触碰
仓库默认的 data/weave.db。直接执行：python3 tests/test_api_loom_fit.py
（也可被 pytest 收集）。
"""

import os
import sys
import tempfile

_TMP_DB = tempfile.NamedTemporaryFile(prefix="weave-test-", suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_PATH"] = _TMP_DB.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.weave import build_interlacing  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


# 声明 3 综 3 踏，但列向量只有 2 种、行向量只有 2 种：
# 矩阵 1 0 1
#      0 1 0
#      1 0 1
REDUNDANT = {
    "name": "redundant 3x3",
    "max_float": 3,
    "threading": [0, 1, 2],
    "tie_up": [[1, 0, 1], [0, 1, 0], [1, 0, 1]],
    "treadling": [0, 1, 2],
}

# 3x3 单位阵：3 种列向量、3 种行向量，无法约简
IDENTITY = {
    "name": "identity 3x3",
    "max_float": 3,
    "threading": [0, 1, 2],
    "tie_up": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "treadling": [0, 1, 2],
}

# 2 经穿在不同原综框上，但列向量完全相同（踏板同时提升两个原综框）
SAME_COLUMN_DIFFERENT_SHAFT = {
    "name": "same column different shaft",
    "max_float": 2,
    "threading": [0, 2],
    "tie_up": [[1, 0, 1]],
    "treadling": [0, 0],
}


def test_loom_fit_endpoint():
    with TestClient(app) as client:
        # 设计不存在 -> 404
        resp = client.post(
            "/designs/99999/loom-fit",
            json={"max_shafts": 4, "max_treadles": 4},
        )
        check(resp.status_code == 404, "missing design returns 404")
        check(resp.json()["detail"] == "design 99999 not found",
              "404 detail message")

        rid = client.post("/designs", json=REDUNDANT).json()["id"]
        original = client.get(f"/designs/{rid}").json()
        matrix = original["audit"]["interlacing"]
        check(matrix == [[1, 0, 1], [0, 1, 0], [1, 0, 1]],
              "redundant fixture matrix as expected")

        # 请求体校验：上限越界 / 缺字段 -> 422（Pydantic 层宽松接受可无损
        # 转换为 int 的 bool/float/str，与既有接口的模型层约定一致）
        bad_bodies = [
            {"max_shafts": 0, "max_treadles": 4},
            {"max_shafts": 65, "max_treadles": 4},
            {"max_shafts": 4, "max_treadles": -1},
            {"max_shafts": 4, "max_treadles": 100},
            {"max_treadles": 4},
            {"max_shafts": 4},
            {},
            {"max_shafts": None, "max_treadles": 4},
            {"max_shafts": 2.5, "max_treadles": 4},
            {"max_shafts": "two", "max_treadles": 4},
        ]
        for body in bad_bodies:
            resp = client.post(f"/designs/{rid}/loom-fit", json=body)
            check(resp.status_code == 422, f"invalid body {body} rejected with 422")

        # 3x3 冗余设计：最少 2 综 2 踏，设备 2x2 适配
        resp = client.post(
            f"/designs/{rid}/loom-fit",
            json={"max_shafts": 2, "max_treadles": 2},
        )
        check(resp.status_code == 200, "loom-fit 200")
        data = resp.json()
        check(data["design_id"] == rid and data["max_shafts"] == 2
              and data["max_treadles"] == 2,
              "echoes design id and equipment limits")
        check(data["original_shafts"] == 3 and data["original_treadles"] == 3,
              "original declared counts")
        check(data["min_shafts"] == 2 and data["min_treadles"] == 2,
              "minimum counts are distinct full column/row vector counts")
        check(data["fits"] is True and data["shafts_fit"] is True
              and data["treadles_fit"] is True,
              "fits when both minima are within limits")
        check(data["shafts_removed"] == 1 and data["treadles_removed"] == 1,
              "one shaft and one treadle removed")
        check(abs(data["shaft_reduction_ratio"] - 1 / 3) < 1e-12
              and abs(data["treadle_reduction_ratio"] - 1 / 3) < 1e-12,
              "reduction ratios relative to the original design")

        draft = data["reduced_draft"]
        check(draft["shafts"] == 2 and draft["treadles"] == 2,
              "reduced draft dimensions")
        check(draft["threading"] == [0, 1, 0],
              "reduced threading groups identical full column vectors")
        check(draft["treadling"] == [0, 1, 0],
              "reduced treadling groups identical full row vectors")
        check(draft["tie_up"] == [[1, 0], [0, 1]],
              "reduced tie_up rebuilt from equivalence classes")
        check(draft["shaft_classes"] == [[0, 2], [1]],
              "shaft classes in first-appearance order")
        check(draft["treadle_classes"] == [[0, 2], [1]],
              "treadle classes in first-appearance order")
        check(draft["interlacing"] == matrix,
              "reconstructed interlacing equals the original point by point")
        # 逐点校验由约简草图确实能还原原矩阵
        rebuilt = build_interlacing(
            draft["threading"], draft["tie_up"], draft["treadling"]
        )
        check(rebuilt == matrix,
              "independent rebuild from reduced draft matches the matrix")

        # 上限恰为最少数量时也算适配（闭区间）
        data = client.post(
            f"/designs/{rid}/loom-fit",
            json={"max_shafts": 2, "max_treadles": 3},
        ).json()
        check(data["fits"] is True and data["treadles_fit"] is True,
              "equality counts as fit (inclusive limits)")

        # 仅综框超限：fits=false，但 treadles_fit 仍为 true
        data = client.post(
            f"/designs/{rid}/loom-fit",
            json={"max_shafts": 1, "max_treadles": 2},
        ).json()
        check(data["fits"] is False and data["shafts_fit"] is False
              and data["treadles_fit"] is True,
              "fits false when shafts minimum exceeds the limit")

        # 仅踏板超限
        data = client.post(
            f"/designs/{rid}/loom-fit",
            json={"max_shafts": 2, "max_treadles": 1},
        ).json()
        check(data["fits"] is False and data["shafts_fit"] is True
              and data["treadles_fit"] is False,
              "fits false when treadles minimum exceeds the limit")

        # 64 上限：约简结果与上限无关，始终适配
        data = client.post(
            f"/designs/{rid}/loom-fit",
            json={"max_shafts": 64, "max_treadles": 64},
        ).json()
        check(data["fits"] is True and data["min_shafts"] == 2
              and data["min_treadles"] == 2,
              "limit 64 fits small designs; minima independent of limits")

        # 3x3 单位阵：3 种列/行向量，无法约简，2x2 设备不适配，3x3 适配
        iid = client.post("/designs", json=IDENTITY).json()["id"]
        imatrix = client.get(f"/designs/{iid}").json()["audit"]["interlacing"]
        data = client.post(
            f"/designs/{iid}/loom-fit",
            json={"max_shafts": 2, "max_treadles": 2},
        ).json()
        check(data["fits"] is False and data["min_shafts"] == 3
              and data["min_treadles"] == 3,
              "identity matrix needs 3 shafts and 3 treadles")
        check(data["shafts_removed"] == 0 and data["treadles_removed"] == 0
              and data["shaft_reduction_ratio"] == 0.0
              and data["treadle_reduction_ratio"] == 0.0,
              "no reduction when all column/row vectors differ")
        draft = data["reduced_draft"]
        check(draft["threading"] == [0, 1, 2]
              and draft["treadling"] == [0, 1, 2]
              and draft["tie_up"] == IDENTITY["tie_up"]
              and draft["interlacing"] == imatrix,
              "irreducible draft is returned unchanged")
        data = client.post(
            f"/designs/{iid}/loom-fit",
            json={"max_shafts": 3, "max_treadles": 3},
        ).json()
        check(data["fits"] is True, "identity fits a 3x3 device")

        # 不同原综框但完整列向量相同：必须归并到同一个约简综框
        cid = client.post("/designs", json=SAME_COLUMN_DIFFERENT_SHAFT).json()["id"]
        cmatrix = client.get(f"/designs/{cid}").json()["audit"]["interlacing"]
        check(cmatrix == [[1, 1], [1, 1]], "all-ones matrix fixture")
        data = client.post(
            f"/designs/{cid}/loom-fit",
            json={"max_shafts": 1, "max_treadles": 1},
        ).json()
        check(data["min_shafts"] == 1 and data["min_treadles"] == 1
              and data["fits"] is True,
              "identical column vectors on different original shafts merge")
        check(data["original_shafts"] == 3
              and data["shafts_removed"] == 2,
              "declaration had 3 shafts (0/1/2), only 1 is needed")
        draft = data["reduced_draft"]
        check(draft["threading"] == [0, 0] and draft["treadling"] == [0, 0]
              and draft["tie_up"] == [[1]]
              and draft["shaft_classes"] == [[0, 1]]
              and draft["treadle_classes"] == [[0, 1]],
              "everything collapses onto reduced shaft/treadle 0")

        # 接口只读：不改库，设计数量与内容均不变
        ids_before = {d["id"] for d in client.get("/designs").json()}
        client.post(f"/designs/{rid}/loom-fit",
                    json={"max_shafts": 1, "max_treadles": 1})
        client.post(f"/designs/{iid}/loom-fit",
                    json={"max_shafts": 64, "max_treadles": 64})
        ids_after = {d["id"] for d in client.get("/designs").json()}
        check(ids_before == ids_after, "loom-fit creates no new designs")
        again = client.get(f"/designs/{rid}").json()
        check(again["threading"] == REDUNDANT["threading"]
              and again["tie_up"] == REDUNDANT["tie_up"]
              and again["treadling"] == REDUNDANT["treadling"]
              and again["shafts"] == 3 and again["treadles"] == 3,
              "loom-fit does not modify the stored design")
        check(again["audit"]["interlacing"] == matrix,
              "loom-fit does not modify the stored audit")


if __name__ == "__main__":
    test_loom_fit_endpoint()
    try:
        os.unlink(_TMP_DB.name)
    except OSError:
        pass
    print("all API tests passed")
