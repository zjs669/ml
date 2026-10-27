"""盘面样本与盘面登记表必须一致。

为什么需要这条断言：`ChartBoard.vue` 的 `BOARDS` 里登记一个专属盘面后，
如果忘了在 `dump_board_facts.py` 加样本，`npm run check:boards` 会静默跳过它 ——
「新增盘面没人验」这件事只能靠人记。这里把两边对起来。

判据是**域名列表**而不是内容：前端 TS 与后端 Python 没有共享的中间格式，
用清单比对是唯一不引入新依赖的做法。Python 侧用 AST 解析（CASES 的值是嵌套字典，
正则会在第一个 `}` 处截断），TS/MJS 侧用正则。
"""

from __future__ import annotations

import ast
import io
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
CHART_BOARD = REPO / "frontend" / "src" / "components" / "chart" / "ChartBoard.vue"
DUMP_SCRIPT = BACKEND / "scripts" / "dump_board_facts.py"
CHECK_SCRIPT = REPO / "frontend" / "scripts" / "check-boards.mjs"

#: 有专属盘面组件但故意不纳入 SSR 冒烟的域，写明原因
EXEMPT: dict[str, str] = {
    # 这四个盘面在接入 ChartFrame 前就有页面级校验，样本由对应 test_*.py 覆盖；
    # 它们的 chart_facts 结构复杂（紫微 12 宫、六爻纳甲），SSR 断言收益低。
    "bazi": "由 tests/test_bazi.py 的基准命例覆盖",
    "ziwei": "由 tests/test_ziwei.py 的 10 例手推基准覆盖",
    "liuyao": "由 tests/test_liuyao_engine.py 覆盖",
    "qimen": "由 tests/test_qimen_engine.py 覆盖",
}


def _registered_boards() -> set[str]:
    """从 ChartBoard.vue 的 BOARDS 对象里取 domain 列表。

    支持两种登记写法，因为盘面组件改成了按域异步加载：

        静态：bazi: BaziBoard,
        异步：bazi: defineAsyncComponent(() => import('./BaziBoard.vue')),

    只认「值里出现 XxxBoard」这一条共同特征，不去解析嵌套括号 ——
    解析 import() 的括号配对只会让测试比被测代码更脆。
    """
    text = CHART_BOARD.read_text(encoding="utf-8")
    start = text.find("const BOARDS")
    assert start >= 0, "ChartBoard.vue 里找不到 BOARDS 定义（结构变了就同步改本测试）"
    end = text.find("}", start)
    assert end > start, "BOARDS 对象没有闭合"
    block = text[start:end]
    pairs = re.findall(r"^\s*(\w+):\s*(.+?)$", block, re.MULTILINE)
    return {key for key, value in pairs if re.search(r"\w+Board\b", value)}


def _dump_domains() -> set[str]:
    """从 dump_board_facts.py 的 CASES 里取 domain 列表（AST 解析，值里有嵌套字典）。"""
    tree = ast.parse(io.open(DUMP_SCRIPT, encoding="utf-8").read())
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not (isinstance(target, ast.Name) and target.id == "CASES"):
            continue
        assert isinstance(node.value, ast.Dict), "CASES 必须是字面量字典"
        return {
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    raise AssertionError("dump_board_facts.py 里找不到 CASES 定义")


def _check_domains() -> set[str]:
    """从 check-boards.mjs 的 boards 对象里取 domain 列表。"""
    text = CHECK_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"const boards = \{([^}]*)\}", text)
    assert match, "check-boards.mjs 里找不到 boards 定义"
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.MULTILINE))


def test_dump_covers_every_registered_board() -> None:
    registered = _registered_boards()
    covered = _dump_domains() | set(EXEMPT)
    missing = sorted(registered - covered)
    assert not missing, (
        f"这些域有专属盘面组件但没导出样本：{missing}。"
        "请在 scripts/dump_board_facts.py 的 CASES 里补一条，或加入本测试的 EXEMPT 并写明理由"
    )


def test_check_script_covers_every_dumped_domain() -> None:
    dumped = _dump_domains()
    checked = _check_domains()
    missing = sorted(dumped - checked)
    assert not missing, f"这些域导出了样本但 check-boards.mjs 没验：{missing}"


def test_exempt_domains_actually_have_boards() -> None:
    """EXEMPT 里写的域必须真的有盘面组件，避免豁免名单变成僵尸配置。"""
    stale = sorted(set(EXEMPT) - _registered_boards())
    assert not stale, f"EXEMPT 里这些域已没有专属盘面，应删掉豁免：{stale}"
