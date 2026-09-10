# 运行与数据契约

脚本使用 Python 3.10+ 标准库，不联网、不读环境密钥，不需要 pip 依赖。
下文的 `SKILL_DIR` / `WORKSPACE` 是由 Agent 解析的绝对路径占位符。命令行参数必须按当前 shell 正确引用；不要把 JD 文本拼入 shell 命令，使用 UTF-8 文件传入。

## 环境与宿主

- 核心：读写文件、运行 Python。首次先用 `python3 --version`（Windows 可用 `py -3 --version`）检查。
- Word/PDF：使用宿主可用的文档提取能力；提取不全时请用户补文本，不把残缺提取当完整档案。扫描 PDF 需要 OCR 能力。
- 浏览器/搜索：可选。JD 粘贴全文即可开展工作；无法读取网页时请补全文。
- 独立审稿：使用全新上下文的子 Agent，只传必要事实、草稿与审稿任务。不能做到时输出待审稿材料和明确的人工恢复入口。
- PDF：使用可用浏览器的打印引擎，A4、关闭页眉页脚。浏览器自动打印可用时自行完成，否则请用户保存 PDF。文本提取不能证明版式合格，换渲染引擎也不能沿用浏览器分页结论。
- 无 Python 时可以做临时的纯对话建议，但明确“未建立持久化工作区”；不手工模拟已完成的状态脚本。

## 目录

```text
WORKSPACE/
  profile.md          # 本人确认的事实，带稳定事实 ID
  preferences.json    # 地点、薪资口径、到岗时间等；未知为 null/空数组
  tracks.md           # 方向假设、样本、补证据行动
  jobs.json           # 岗位与投递事件的唯一状态源
  diagnosis/          # 按日期/版本保存诊断及样本
  inputs/             # 用户授权读取的简历、JD、临时结构化输入
  applications/job-<hash>/v001/
    jd.md
    assessment.json
    resume.html
    resume.pdf        # 浏览器打印后生成；未生成时明确缺失
    resume.txt
    messages.md
    audit.md
    checks.json
```

`init` 不覆盖现有资料，不自动导入旧版个人项目。若已有旧版档案，先列出拟迁移资料并在用户明确指定后读取，原档案和已投归档保留。
脚本初始化的 `.gitignore` 是防误提交辅助，不代表文件从不离开电脑：宿主模型可能接收用户提供的内容。不要声称全离线或绝不上传；遵守用户选择的模型和资料范围。

## 命令接口

```sh
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" init
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" rank --input "WORKSPACE/inputs/jobs.json"
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" list --actionable
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" prepare --job JOB_ID --request-id REQUEST_ID
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" ready --job JOB_ID --revision v001
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" applied --job JOB_ID --revision v001 --date YYYY-MM-DD --confirmed
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" event --job JOB_ID --event-id EVENT_ID --kind interview --date YYYY-MM-DD --note "一面已约"
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" followups --days 10
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" export --output "WORKSPACE/tracker-export.csv"
```

脚本输出 JSON。`--confirmed` 只表示用户已明确确认事情发生，Agent 不得自行补这个事实。
`REQUEST_ID` 与 `EVENT_ID` 在同一操作重试时不变（可用 UUID）；新一轮修改使用新值。`prepare` 返回目录后在该目录填稿，不自行猜目录。
同一请求重试返回原版本；新请求创建新版本；已投版本不能通过该请求重新打开修改。不要编辑 `applied_revision` 指向的文件，准备新版本供后续使用。

`ready` 检查必需文件、检查记录格式、独立审稿与一致性通过标记，并记录材料摘要；后续提交时核对材料未被更改。它不替代内容审核，脚本不会判断 claim 是否真实。只有 Agent 完成 apply 的审计步骤才能调用；改稿后须复核并重新 ready。
`jobs.json` 由脚本写入，先校验整批输入再原子替换。CSV 仅是导出视图，不手工双向同步。导出拒绝覆盖现有文件，并转义公式前缀。

## 岗位身份与排序输入

输入是数组，每个岗位最少需要 `company`、`title`、`jd`，其他字段见 [示例](../assets/sample-jobs.json)。
来源写入 `source`：type（user_paste / user_screenshot / web / unspecified 等文本）、date（采集日期或 null）、path（工作区相对来源位置）、note（备注）、verified_hiring（是否实际核实在招，未知为 null）。路径只是来源标记，不会被脚本自动读取。
逐维依据写入 `score_rationale`，键名与 scores 相同，值为包含 JD 原文与事实 ID 的说明；未知项说明缺什么。来源与评分依据会一起写入状态和 assessment.json 快照。脚本拒绝未支持的输入字段，防止静默丢失。
身份由公司、岗位、地点与 `requisition_id` 计算；URL 查询参数不改变身份。同公司同名同地的不同招聘批次，必须填写不同 requisition_id；区分不了先问用户，不能猜着合并。
完整 JD 保存在状态中；每次准备材料时快照到版本目录。重新评估更新当前岗位信息，不改旧版本的 JD 和评估。

`scores` 五项：资格 / 经验 / 技能 / 契合 / 发展。每项 0–5 整数或 null。权重固定为 4/6/5/3/2，满分 100；所有方向共用，缺任一项则总分 null。该权重只是排序启发式，解释见 evaluation.md。
`deal_breaker: true` 必须提供 `deal_breaker_quote`，且为 JD 内逐字原文；脚本核对原文存在，Agent 负责核对用户约束是否真的冲突。
`deadline` 接受 YYYY-MM-DD；非法值/模糊值保留在 `deadline_raw`，有效字段置 null，不猜。仅早于当前本地日期才过期，当天仍有效。`list --actionable` 排除已投、硬否决、过期与主动关闭的岗位。

## 状态与恢复

`ranked → preparing → prepared → applied → read / interview / offer / rejected / withdrawn / closed / no_response`

`reply` 只记录活动，`followup_sent` 只记录真实跟进，不改变投递阶段。跟进计时取投递和全部已记录活动中的最近日期，默认超过 10 天且已发跟进少于 2 次。
过期只作为筛选标记，不自动把已投申请变成被拒。事件带 ID，可重试且不重复；历史事件按发生日期决定当前阶段。
同一工作区同时只允许一个状态写入；遇锁先检查另一任务，确认已停止才处理残留锁。状态损坏时报错保留原文，不清空重置。中断后先 `list` 并检查版本目录；未登记的孤立版本保留，下一次准备会分配新的未占用目录。
