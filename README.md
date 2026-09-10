# Job Assistant · 中文求职助手

把真实经历整理成有依据的岗位判断、简历和面试材料。适用于支持本地文件与脚本的 AI Agent。

**它会帮你准备申请材料；不会替你投递或发送消息。** AI/数字化转型是可选场景，其他职业背景也可以使用。

## 你可以直接这样说

- “这是我的简历，先帮我整理真实经历和需要补充的证据。”
- “我想做实施顾问，帮我判断这三份 JD 哪个更适合。”
- “按这份 JD 改简历，同时给我平台能粘贴的纯文本和开场白。”
- “我已经投了第二版简历，帮我登记。下周一是一面，帮我准备。”

不必先学六条命令，也不必每次跑完整套流程。

## 能做什么

| 模式 | 作用 | 主要产物 |
|---|---|---|
| setup | 从简历或访谈建立事实档案 | 已确认事实、来源、偏好 |
| diagnose | 用真实 JD 验证求职方向 | 匹配证据、差距、补证据行动 |
| rank | 批量筛选岗位 | 有依据的排序与待确认项 |
| apply | 定制申请材料并独立审稿 | HTML / PDF、纯文本、话术、审计 |
| interview | 围绕实际提交版本准备面试 | STAR、追问、公司信息、模拟面 |
| outcome | 记录实际投递和后续进展 | 事件、状态、跟进草稿 |

## 安装

需要 Python **3.10+** 和具备本地文件读写、命令执行能力的 Agent。脚本仅用标准库，不需要 pip 安装。

下载或 clone 本仓库后，安装的是 **`skills/job-assistant` 整个目录**，不是只复制 SKILL.md。不要将自己的简历放进这个安装目录。

### Claude Code

将 `skills/job-assistant` 复制到目标项目的 `.claude/skills/job-assistant`，或个人 Skill 目录 `~/.claude/skills/job-assistant`。目标已存在时先保留旧版，不直接覆盖其中可能存在的用户资料。

在会话里请求使用 `job-assistant`。若没有自动加载，可明确要求读取安装后的 `SKILL.md`。不依赖旧版 `.claude/commands`。

### Codex

将 `skills/job-assistant` 复制到 `~/.codex/skills/job-assistant`，重新开始会话后使用 `$job-assistant`。如果已有同名版本，先保留旧版；自定义了 Skill 根目录的环境使用其配置目录。

### Kimi Code CLI 或其他本地 Agent

将整个目录放在本地固定位置，在会话里明确告诉 Agent：

> 读取这里的 `skills/job-assistant/SKILL.md`，按其中流程处理我的求职任务。个人数据使用另一个 `job-search-data` 目录。

这是一条不依赖宿主自动发现机制的入口。是否原生注册 Skill、支持独立子 Agent 和读取 PDF，以实际安装版本为准。

## 第一次使用

告诉 Agent 两件事：**本次使用的资料位置**和**求职数据保存目录**。尚无简历也可以对话建档。

例如：“使用这个 Skill。我的求职资料放在独立的 job-search-data 目录；先访谈我，建立事实档案。”

Agent 会初始化空白档案与偏好。只对影响当前任务的缺失信息提问；未确认事实不会写入对外材料。每位使用者各用一个工作区，避免资料混用。

手动检查脚本入口（将路径换为实际安装位置；Windows 可用 `py -3`）：

```sh
python3 skills/job-assistant/scripts/workspace.py --workspace ../job-search-data init
python3 skills/job-assistant/scripts/workspace.py --workspace ../job-search-data list
```

## 数据放在哪里

```text
Skill 安装目录                 个人求职工作区（安装目录外）
  SKILL.md                       profile.md
  references/                    preferences.json / tracks.md
  scripts/                       jobs.json
  assets/                        applications/<岗位ID>/<材料版本>/
  agents/                        diagnosis/ / inputs/
```

Skill 包只包含流程、空白模板、脚本和虚构示例。用户资料写在独立工作区，不应提交到此仓库。

本地脚本不联网。**模型是否接收资料取决于你使用的 Agent 和模型服务**；文件在本地不等于模型推理完全离线。请只提供你允许该服务处理的资料，未经许可的客户信息不要放入对外简历或网络查询。

## 怎样保证材料可信

- 每条对外事实有本人已确认的档案出处，检查角色、动词、数字、归因和公开范围。
- 简历、纯文本与话术一起独立审稿。没有独立上下文能力时明确停在“待审稿”，不能自称通过。
- 生成材料记为“已准备”，用户确认实际提交后才记“已投”。跟进草稿不算已经发送。
- 新修改另开版本，已投版本保留。重复操作使用同一请求 ID，不反复新建记录。
- 匹配分是有解释的排序建议，不是录用概率；未知信息单独标注，不用零分替代。

## 环境能力与限制

| 能力 | 缺失时如何处理 |
|---|---|
| Python 3.10+、文件读写 | 无法使用持久化流程；仅可临时做对话建议 |
| 简历文本提取 / OCR | 请用户补充文本，不假装已经完整读取 |
| 浏览器 / 搜索 | 使用粘贴 JD；公司调研标未核实 |
| 独立子 Agent / 独立会话 | 保留草稿和审稿请求，标待独立审稿 |
| 浏览器 PDF 打印与读图 | 先交 HTML / 纯文本，PDF 分页标未验证 |
| PDF 文本提取 | 标文本层未检查，不宣称 ATS 通过 |

目前自动化测试覆盖本地数据与归档行为；**不代表 Claude Code、Kimi Code CLI、Codex 三端完整求职流程均已实测通过**。上线模型、文档读取、PDF 渲染和新用户语言效果按 [验收场景](tests/skill/ACCEPTANCE.md) 单独验证。

## 开发与验证

```sh
python3 -m unittest discover -s tests/skill -p 'test_*.py' -v
python3 tools/build_release.py --output ../job-assistant-release
```

发布工具只复制 `release-files.txt` 明确列出的文件，不携带 `.git` 历史、旧个人项目或运行数据。输出目录必须不存在；新增发布文件需要更新清单并审查。它不自动推送、不声称能检测所有隐私。

详细接口见 [运行契约](skills/job-assistant/references/runtime.md)，Skill 入口见 [SKILL.md](skills/job-assistant/SKILL.md)，本版实测范围见 [验证记录](tests/skill/VALIDATION.md)。

## 许可与致谢

MIT，见 [LICENSE](LICENSE)。求职流程参考 [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)，来源说明见 [NOTICE.md](NOTICE.md)。
