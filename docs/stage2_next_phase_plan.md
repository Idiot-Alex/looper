# OPC 下一阶段建议（Stage 2 规划冻结版）

基于 `docs/opc_stage1_final_frozen_spec.md`，Stage 1 已经明确聚焦在单机闭环与可审计执行。下一阶段建议目标不是“加更多角色”，而是把可运行 MVP 升级为**可持续稳定运行的工程系统**。

## Stage 2 目标

把 Stage 1 的“能跑通一次”升级为“可以连续跑、多任务跑、失败可恢复、可观测、可治理”。

---

## 建议优先级（P0 / P1 / P2）

## P0（先做，决定是否能工程化）

1. **任务队列化（从单任务到多任务）**
   - 把 `opc/tasks/inbox.md` 单输入改为队列输入（例如 `inbox/` 目录 + 每任务独立 session id）。
   - 每个任务独立状态文件，避免互相覆盖。

2. **任务调度策略（Stage 2 明确钉死）**
   - 默认策略：**FIFO（按写入时间升序）**。
   - 同时写入导致时间相同：按文件名字典序作为稳定 tie-breaker。
   - Stage 2 不做复杂依赖图调度；只支持单队列串行执行。
   - 可选字段 `priority` 仅预留，不在 Stage 2 生效（避免隐式复杂度）。

3. **幂等与断点恢复**
   - Runner 异常退出后可从最近安全状态恢复。
   - Stage 2 固定最小实现：在 `status.json` 中新增 `completed_stages` 数组，例如 `"completed_stages": ["manager", "engineer"]`。
   - Runner 启动时先读取 `completed_stages`，已完成阶段直接跳过，仅执行未完成阶段（与 Stage 1 状态机兼容）。
   - 保留“回放保护”：对写文件与命令执行增加去重标记，避免重复落地与重复执行。

4. **命令执行沙箱强化（含 session 全局超时）**
   - 现有白名单基础上加入：
     - 每条命令资源限制（CPU/内存/时长）
     - 工作目录强约束
     - 网络访问策略（允许/禁用/域名白名单）
     - **session 级全局 timeout**（例如 15 分钟），超时后终止当前任务并清理后台进程，释放队列。
   - **任务交接前必须验证端口和资源已释放**，通过后才能 dequeue 下一个任务，避免前一个任务清理不彻底导致端口冲突或资源泄漏。

5. **结构化运行日志（机器可查询）**
   - 保留文本日志，同时增加结构化 JSONL 事件流。
   - 关键事件统一 schema：`session_start`、`llm_call`、`file_write`、`command_run`、`qa_decision`、`session_timeout`。

## P1（紧跟 P0，提高质量与效率）

6. **差量写入策略（Stage 2 保守版）**
   - Stage 2 **不引入 LLM 直出 patch 应用**，继续以“完整文件覆盖”为主，降低 apply 失败风险。
   - 先实现 Runner 侧最小改动保护：写入前后 diff 摘要、语法检查、关键测试子集 pre-check。
   - patch/unified diff 作为 Stage 3 候选能力。

7. **验收策略模板化**
   - 给 Manager 增加任务类型模板（web/api/cli/script）。
   - 自动补齐推荐测试命令，减少 test_commands 质量波动。

8. **本地 Git 快照（提前到 P1）**
   - 每轮落地代码后自动创建本地 commit（不做 PR 自动化）。
   - commit 信息至少包含 session id、task id、阶段与摘要，支持快速回滚与任务隔离审计。

9. **QA 判定可解释性升级**
   - `qa_report.json` 除 pass/fail 外，新增：
     - criterion-by-criterion 逐条判定
     - 风险等级（high/medium/low）
     - 建议修复优先级

10. **重试策略精细化**
   - 不是固定 3 次重试：按失败类型动态重试。
   - 失败类型由 **QA** 负责分类，并在 `qa_report.json` 输出 `failure_type` 字段。
   - `failure_type` 枚举固定为：`compile_error / test_failure / timeout / unknown`。
   - `protocol_error` 不由 QA 产出：由 Runner 在解析层单独处理，并写入 `status.json`（对应 Stage 1 的 `parse_error` 路径）。
   - Runner 根据 `failure_type` 选择对应修复 prompt 模板。

## P2（后续扩展，非阻塞）

11. **成本与时延治理**
   - 记录每轮 token、耗时、失败原因分布。
   - 引入模型降级/升级策略（先便宜模型，失败再升级）。

12. **简单可视化面板**
   - 展示 session 状态、阶段耗时、失败热区。
   - 先只读展示，不做复杂控制面。

---

## 建议里程碑（4 周）

- **Week 1**：任务队列 + 调度规则（FIFO）+ 独立状态文件 + 断点恢复（P0）
- **Week 2**：执行沙箱（含 session 全局 timeout）+ 结构化日志（P0）
- **Week 3**：验收模板化 + 本地 Git 快照 + QA 可解释性（P1）
- **Week 4**：差量写入保守版 + 重试精细化 + 指标看板基础（P1/P2）

---

## 完成判定（Stage 2 Exit Criteria）

达到以下标准可认为 Stage 2 完成：

1. 支持连续处理多个任务，任务间状态互不污染。
2. 队列调度顺序可预测（FIFO + 文件名字典序 tie-breaker）。
3. Runner 在异常中断后可恢复，不重复执行已完成阶段。
4. 命令执行具备明确安全边界、命令级超时与 session 级全局超时控制。
5. 任一 session 可通过结构化日志完整追溯，并可识别 timeout/cleanup 事件。
6. 具备每轮本地 Git 快照，可按任务快速回滚。
7. QA 报告可逐条对应验收标准并给出修复优先级，且包含 `failure_type` 枚举字段（不含 `protocol_error`）。
8. 失败分布和成本/时延指标可被统计并用于优化。

---

## 一句话建议

**Stage 2 先把可靠性“做硬”：队列、恢复、超时、审计、回滚；patch 智能化留到 Stage 3。**
