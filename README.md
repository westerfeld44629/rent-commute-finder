# rent-commute-finder

通勤约束型租房 Skill / MCP，面向 **WorkBuddy、Codex 等本地 Agent**。输入办公楼、通勤时间、预算和独卫/电梯要求，输出本轮候选的**逐套房源全表、推荐与匹配审计**。

**当前版本：1.1.1 预览版。** 已具备筛选、报告和本地 MCP 工具；真实房源检索、办公楼定位与地图查询由宿主工具或授权数据源提供。本仓库不自带房源数据库、平台爬虫或地图 Key，独立运行 MCP 不会自动搜索真实房源。

[使用示例](#使用示例) · [安装为-skill](#安装为-skill) · [命令行快速体验](#命令行快速体验) · [mcp-接入](#mcp-接入) · [完整演示报告](examples/demo-report.md)

## 工作方式

```text
自然语言需求
  → Agent 解析办公地点 / 方式 / 预算 / 硬条件
  → 宿主检索真实房源、定位楼栋、取得通勤路线证据
  → 本项目逐套去重、筛选与排序
  → report.md + listings.csv + report.json
```

| 能力 | 当前行为 |
|---|---|
| 预算与设施 | 月租或总月支出、独卫、电梯；缺证据为未知 |
| 通勤 | 公交、电动车等分开判断；支持全部达标或任一种达标 |
| 去重 | 按平台房源 ID / 详情 URL，同小区不同房间保留 |
| 结果状态 | 符合、待核实、不符合，三类都保留在全表 |
| 推荐 | 只从符合项中选最多 3 套，按保守通勤时间、预算金额排序 |
| 数据审计 | 来源链接、核验时间、短证据、重复数量及排除原因 |
| MCP | 输入契约、证据评估，支持 JSON / Markdown / CSV |

“房源全表”指**本轮实际检索或输入的全部唯一候选**，不承诺全网覆盖。没有检索能力或足够证据时，如实输出缺口或空结果。

## 使用示例

安装 Skill 后，在 Agent 中输入：

```text
请使用 rent-commute-finder 技能。

我在xx市，办公地点在xx办公楼（虚构地址），
通行时间需要控制在一个小时以内（公共交通和电动车），
价格在2500以内，独卫，需要有电梯。

请输出本轮检索到的房源全表，以及符合条件的推荐。
每套保留原链接、核验时间、独卫和电梯证据、两种通勤时间及计算口径。
未知条件单列待核实，表格太长时给我完整CSV。
```

默认解释如下，报告中会披露这些假设：

| 字段 | 解释 |
|---|---|
| 办公锚点 | 示例地址为虚构占位；实际使用时提供具体办公楼，入口不能代替楼门 |
| 通勤 | 公交和电动车**均不超过 60 分钟**，默认工作日高峰 |
| 预算 | 月租 ≤2500 元，水电/服务费等另列缺口 |
| 必须条件 | 该房间独卫、该楼栋有电梯 |
| 居住范围 | 按可达性搜索，不默认限定在办公地点所在行政区 |
| 未指定条件 | 不擅自添加整租、朝向、最低面积等限制 |

可以继续补充：

```text
公交和电动车任意一种在一小时内即可。
```

或：

```text
2500是总月支出，包含固定服务费等；未确认的费用不要当作已经符合。
```

第一句对应 `mode_policy=any`；第二句对应 `budget_basis=monthly_total`。这些变化只影响本轮需求，不修改其他用户的规则。

### 输出长什么样

下面是随包合成输入的完整 8 套候选摘要，**不是真实挂牌**。实际报告还包含设施证据、通勤口径、原链接、核验时间及缺口。

| 编号 | 合成房间 | 月租 | 公交 | 电动车 | 状态 | 原因 |
|---|---|---|---|---|---|---|
| R0003 | 房间2，同小区另一间 | 2100 | 40～50分 | 40～50分 | 符合 | 输入证据满足条件 |
| R0001 | 房间1 | 2300 | 40～50分 | 40～50分 | 符合 | 输入证据满足条件 |
| R0004 | 房间3 | 2300 | 40～50分 | 40～50分 | 待核实 | 电梯未知 |
| R0007 | 房间6 | 2300 | 40～50分 | 40～50分 | 待核实 | 只有搜索摘要 |
| R0008 | 房间7 | 2300 | 40～50分 | 40～50分 | 待核实 | 电动车仅模型估算 |
| R0009 | 房间8 | 2300 | 40～50分 | 40～50分 | 待核实 | 房源证据已过期 |
| R0006 | 房间5 | 2300 | 40～50分 | 70～75分 | 不符合 | 电动车超时 |
| R0005 | 房间4 | 2600 | 40～50分 | 40～50分 | 不符合 | 超预算 |

在这个合成例子中，推荐依次是 R0003、R0001：两套通勤上界相同，R0003 月租更低。未知水电/服务费仍列为缺口，设施仍需现场确认。

审计：9 条输入 → 去重 1 条 → 8 套唯一候选；符合 2、待核实 4、不符合 2。房间1和房间2虽然在同一小区，仍分别保留。

- [完整合成报告](examples/demo-report.md)
- [完整候选 CSV](examples/demo-listings.csv)
- [结构化结果 JSON](examples/demo-report.json)
- [合成输入 JSON](examples/demo-input.json)
- [虚构场景说明](examples/commute-rental-demo.md)

公开示例的城市、办公楼、小区、车站、价格和路线均为虚构或合成数据，使用 `.invalid` 域名，不可用于租房决策。实际使用时在本地填写自己的地点和真实证据，不要把个人地址、坐标或任务报告提交到公开仓库。

## 安装为 Skill

### 下载项目

```powershell
git clone https://github.com/westerfeld44629/rent-commute-finder.git
cd rent-commute-finder
```

也可以从 [1.1.1 预览版发布页](https://github.com/westerfeld44629/rent-commute-finder/releases/tag/v1.1.1-preview) 下载 `rent-commute-finder-1.1.1-preview.zip` 和 `SHA256SUMS.txt` 后解压。安装时保留完整目录，不能只复制 `SKILL.md`。

### Codex

把完整项目目录放到以下任一位置：

- 个人技能：`~/.agents/skills/rent-commute-finder/`
- 项目技能：`<project>/.agents/skills/rent-commute-finder/`

例如，在目标项目根目录执行：

```powershell
git clone https://github.com/westerfeld44629/rent-commute-finder.git .agents/skills/rent-commute-finder
```

在新会话中输入前面的示例提示词，明确要求使用本技能。目录发现规则见 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

### WorkBuddy

将完整 `rent-commute-finder` 目录放入当前版本指定的技能目录。本机已有 `~/.workbuddy/skills/`；其他版本请以客户端实际约定为准。重新打开会话后，明确要求 Agent 使用本技能。

本轮没有完成 WorkBuddy/Codex 内的真实找房流程，不能把目录存在或脚本测试通过当成宿主端验收。

### 运行前准备

- Python 3.10 或以上，所有配套脚本通过虚拟环境解释器执行。
- 核心筛选和报告只用标准库，**只使用 Skill / CLI 无需安装 MCP 依赖**。
- 宿主需有网页检索/读取能力，或用户提供可追溯房源证据。
- 精确通勤依赖宿主地图工具或授权路线数据；缺失时只能输出待核实。
- 路径按技能所在目录解析，不依赖开发者电脑路径。输出存到当前任务目录，不把真实房源证据提交到本仓库。

## 命令行快速体验

先安装 Python 和 uv，下面以已安装的 Python 3.13 为例。命令不需要激活环境，也不更改环境变量；未使用 uv 时可用现有 Python 管理器创建独立虚拟环境。

### Windows / PowerShell

在仓库根目录执行：

```powershell
uv venv .venv --python 3.13
.\.venv\Scripts\python.exe scripts/find_rentals.py --input examples/demo-input.json --output-dir reports/demo --as-of 2026-10-19T09:00:00+08:00
```

### macOS / Linux

```bash
uv venv .venv --python 3.13
.venv/bin/python scripts/find_rentals.py --input examples/demo-input.json --output-dir reports/demo --as-of 2026-10-19T09:00:00+08:00
```

生成：

```text
reports/demo/
├── report.md       完整可读报告
├── listings.csv    全部唯一候选，可用Excel打开
└── report.json     结构化结果、推荐及审计
```

`--as-of` 仅用于固定日期的离线样例回放。真实输入必须省略，按当前时间检查证据是否过期。

### 使用自己的数据

让宿主按 [输入契约](references/data-contract.md) 和 [JSON Schema](references/input.schema.json) 整理真实证据，保存到本地 `work/my-input.json`，然后执行：

```powershell
.\.venv\Scripts\python.exe scripts/find_rentals.py --input work/my-input.json --output-dir reports/my-search
```

核心结构如下，`listings` 中填写逐套证据；空列表会诚实输出零结果：

```json
{
  "requirements": {
    "city": "xx市",
    "office": "xx办公楼（虚构地址）",
    "budget_max": 2500,
    "budget_basis": "rent",
    "commute_max_min": 60,
    "modes": ["transit", "ebike"],
    "mode_policy": "all",
    "time_window": "weekday_peak",
    "must_have": ["private_bath", "elevator"]
  },
  "listings": []
}
```

完整房源与路线字段见 [合成输入](examples/demo-input.json)。真实输入不应复制合成价格、证据或路线；测试数据始终保留 `synthetic=true`。

## MCP 接入

Skill可直接调用脚本，MCP是可选方式。它处理宿主提交的证据，**没有自动搜索房源、地理编码或地图请求工具**。

### 安装依赖与验证

先完成前面的虚拟环境创建，再执行：

```powershell
uv pip install --python .venv/Scripts/python.exe -i https://mirrors.aliyun.com/pypi/simple/ -r requirements-mcp.txt
.\.venv\Scripts\python.exe tests/mcp_smoke.py
```

macOS/Linux替换为 `.venv/bin/python`。本版固定使用 `mcp==1.30.0`，安装在本项目虚拟环境中。

### Codex 配置示例

按 [OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)，在客户端相应配置中添加以下片段。替换为自己的解压/克隆绝对路径，不要直接使用示例路径：

```toml
[mcp_servers.rent-commute-finder]
command = "C:/tools/rent-commute-finder/.venv/Scripts/python.exe"
args = ["C:/tools/rent-commute-finder/scripts/mcp_server.py"]
```

### JSON 型客户端配置示例

适用于接受 `mcpServers` 格式的客户端；WorkBuddy请以当前版本配置格式为准：

```json
{
  "mcpServers": {
    "rent-commute-finder": {
      "command": "C:/tools/rent-commute-finder/.venv/Scripts/python.exe",
      "args": ["C:/tools/rent-commute-finder/scripts/mcp_server.py"]
    }
  }
}
```

macOS/Linux的 `command` 使用完整的 `.venv/bin/python` 路径。服务通过stdio由客户端启动，不需要监听公网端口，也不把普通日志写到协议stdout。

### 工具与调用示例

| 工具 | 用途 |
|---|---|
| `get_rental_input_contract()` | 读取输入Schema与采集规则 |
| `evaluate_rentals(payload, output_format="json")` | 返回全量结构化评估 |
| `evaluate_rentals(payload, output_format="markdown")` | 返回报告正文 |
| `evaluate_rentals(payload, output_format="csv")` | 返回完整候选CSV正文 |

可以对宿主说：

```text
先调用 get_rental_input_contract。
使用你已有的网页与地图工具采集本次需求的真实证据，
按契约整理后调用 evaluate_rentals，output_format使用markdown。
再导出完整CSV，并说明检索覆盖范围和待核实项。
如果工具不足，不要编造搜索结果。
```

MCP按调用时的当前时间核验数据；旧合成输入可能因过期进入待核实。固定统计回放请用前面的CLI命令；`mcp_smoke.py` 会为合成测试更新时间，不访问真实平台。

## 匹配规则与限制

- 多方式默认全部达标（all），明确任选一种才用any；不擅自放宽预算或设施条件。
- 预算默认月租；要求完整总月费用时，费用缺证据不能判符合。押付、佣金和一次性费用仍需单列确认。
- 独卫、电梯都需要该房间/楼栋的短证据，不能用“高层”“一卫”或筛选参数推断。设施为挂牌方自述，脚本不能验证证据真假。
- 默认房源证据48小时、路线24小时有效，属于可调工程策略，不是平台保证。
- 导航是预测；模型估算、路线禁行未知、时段不符、起终点不匹配或缺少有依据的时间上界进入待核实。时间比较不先四舍五入。
- 当前只自动验证独卫、电梯；宠物、明火、租期等其他硬条件需人工/采集端补审。
- 严格符合项为零时不凑数，不把历史示例当成真实房源。不输出个人联系方式、凭据或整页原文，不代联系、签约、付款。
- 平台被拦时不破解验证码，不连续探测房源ID。规模对外服务需先确认第三方数据与地图授权。

## 开发验证与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests/mcp_smoke.py
.\.venv\Scripts\python.exe scripts/build_release.py --output-dir dist
```

已通过47项逻辑回归、真实stdio握手/工具发现/调用、解压后CLI/MCP检查。这些检查不等于实际宿主找房验收。`evals/cases.json`是Agent行为场景，尚未全部跑实网测试。

打包生成预览ZIP、逐文件manifest及SHA256校验值；排除虚拟环境、工作目录、报告目录和本地证据。原 `commute_calc.py --demo` 仅是片区里程估算，不是房源筛选结果。

## 目录

```text
SKILL.md                      Agent入口
scripts/rental_core.py        筛选与报告引擎
scripts/find_rentals.py        CLI导出
scripts/mcp_server.py          stdio MCP
scripts/build_release.py       允许列表打包
references/                   输入契约、模型口径、平台接入
examples/                     合成输入与完整输出示例
tests/                        逻辑回归、MCP真实握手
```

## 后续计划

1. 接通授权房源入口、楼栋/出入口定位、公交与电动车路线工具。
2. 在取得授权的实际场景中完成WorkBuddy/Codex端到端验收，再扩展不同城市；公开材料只保留虚构案例。
3. 完成干净机器安装、平台/地图授权与商用配额验证；按需要封装为可分发插件或托管MCP。

当前上传用于分享源码、说明和预览试用，不代表登记到Skill/MCP商店或已完成真实找房验收。详细开发证据见 [阶段记录](PHASE_REPORT.md)。

## 许可

原创代码与文档使用 [MIT License](LICENSE)。第三方房源、地图、图片需遵循各自授权。
