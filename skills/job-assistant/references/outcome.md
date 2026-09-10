# outcome：记录真实进展与跟进

读取 runtime.md，先 list 定位 job ID；同名多个岗位让用户选，不凭公司名直接改整批。

## 已经投递

用户明确说“已投/已发送简历”，核对实际版本与日期，再执行 `applied --job ... --revision ... --date ... --confirmed`。用户说“准备投”“稍后发”不能登记。
此前没有材料归档的外部申请：先登记 JD（取不到时使用明确的“原 JD 不可得”说明），请用户给实际提交材料并建归档。不得用后来生成的简历冒充已投版本；在取得并核对之前只说明缺口，不伪造完整记录。

## 收到结果

使用 event 记录已读、约面、面试中、offer、拒绝、主动撤回、岗位关闭、用户决定不再跟进等。CLI kind：`read / interview / offer / rejected / withdrawn / closed / no_response`。
普通回复用 `reply`，详细轮次写 note。记录真实发生日期和反馈，保留原话并注明回忆的不确定性。事件 ID 重试保持不变，修正历史内容需先报告差异，不用重复事件覆盖事实。
`offer` 表示收到录用意向，不代表接受；接受/拒绝的实际决定写备注，不替用户答复。

## 跟进草稿

`followups --days 10` 列出仍进行中、最近活动超过十天、已发送跟进少于两次的申请；看最近回复/面试活动，不只看最初投递日。
用户选定后基于已投材料起草两三句：岗位、已有价值证据、询问推进情况。保存到该申请独立的 followups 目录，用未占用文件名；**不调用发送工具**。
草稿满意、用户表示会发，都不计发送。仅确认已经发出后执行：

```sh
python3 "SKILL_DIR/scripts/workspace.py" --workspace "WORKSPACE" event --job JOB_ID --event-id EVENT_ID --kind followup_sent --date YYYY-MM-DD --confirmed
```

两次仍无回复时提示用户是否结束跟进，不自动判断被拒。更新后汇报状态与已记录事实；若出现一批相似失败，建议 diagnose 复查假设，不能因为一次拒绝就改写职业定位。
