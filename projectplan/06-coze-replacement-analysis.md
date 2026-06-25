# Coze 替代方案分析

> 讨论：是否用其他方案替代 Coze 作为工作流编排层？有哪些选项？推荐什么？

---

## 一、Coze 在我们的架构中到底做了什么

回顾 `01-architecture-overview.md` 的三层架构，Coze 承担的是 **工作流层**：

```
Coze 负责：
  定时触发 / 手动触发（群聊@Bot）
    → 并行扫描7平台热点（6路搜索）
    → 合并去重（Python代码）
    → 知识库RAG + LLM规则评估 + 三维打分
    → 生成19字段选题Brief（Markdown）
    → 飞书卡片消息推送到群聊
```

拆成技术能力清单：

| 能力 | Coze 实现方式 | 是否可替代 |
|------|--------------|:---------:|
| 定时触发 | Coze内置 cron 触发器 | 是 |
| 手动触发（群聊@Bot） | 飞书事件订阅 + 对话触发词 | 较难 |
| Web搜索（6平台） | Coze 插件：必应搜索 / Web Search | 是 |
| 数据合并去重 | Coze 代码节点（Python 3） | 是 |
| 知识库RAG | Coze 知识库（自动分块+混合检索） | 是 |
| LLM推理+评估 | Coze LLM节点（支持多种模型） | 是 |
| 结构化输出 | LLM节点输出JSON → 代码节点解析 | 是 |
| Markdown生成 | LLM节点生成Brief文本 | 是 |
| 飞书卡片推送 | Coze 飞书机器人插件 | 是 |
| 托管运行 | Coze 云端执行，无需维护服务器 | 部分 |

---

## 二、替代方案对比

### 方案A：Claude Code 原生（推荐）

**思路**：全部用 Claude Code 自带工具实现，不引入新平台。

**架构变化**：

```
Coze 工作流层            →    Claude Code Agent + Cron
  ┌──────────┐               ┌──────────────────────┐
  │ 定时触发  │               │ CronCreate (durable)  │
  │ 并行搜索  │               │ WebSearch × 6        │
  │ 合并去重  │               │ Bash: python dedup   │
  │ 规则评估  │               │ Agent (LLM) 评估     │
  │ 生成Brief │               │ Write: topic-brief.md │
  │ 飞书推送  │               │ Bash: curl 飞书Webhook│
  └──────────┘               └──────────────────────┘
```

**具体映射**：

| Coze 功能 | Claude Code 替代 | 实现方式 |
|-----------|-----------------|---------|
| 定时触发 | `CronCreate` (durable: true) | 工作日 9:27 + 14:13 触发 Agent |
| 并行搜索 | `WebSearch` 调用6次 | Agent 内顺序或并行（取决于工具限制） |
| 合并去重 | `Bash` 执行 Python 脚本 | 脚本存在 `agent/scripts/dedup.py` |
| 知识库读取 | 直接 `Read` AI_Writing_Vault 文件 | 无需RAG，完整上下文 |
| LLM推理+评估 | Agent 自身的推理能力 | Prompt 内嵌评估规则 |
| 生成 Brief | `Write` 工具输出 Markdown | 存到 `outputs/topic-briefs/` |
| 飞书推送 | `Bash` curl 飞书 Webhook | 飞书自定义机器人 webhook URL |
| 群聊@Bot触发 | **不支持**，改用 CLI 手动触发 | `claude` 命令或定时触发 |
| 已发文章去重 | `Read` codexarticles/ 目录 | Agent 读最近文章做对比 |

**优点**：
- 零新平台依赖，全部在 Claude Code 内完成
- 知识库不需要同步（直接读本地文件，始终最新）
- Prompt 和逻辑版本受 Git 管理，可审计可回滚
- 不需要学习 Coze 平台操作
- 不需要付费 Coze 订阅
- 开发和调试在同一环境（vs Coze 需要来回切换）

**缺点**：
- 没有群聊 @Bot 交互（只能定时+CLI手动触发）
- CronCreate durable 需要 Claude Code 进程在运行
- 飞书交互从"卡片按钮"降级为"webhook 纯文本消息"
- WebSearch 的质量和覆盖范围取决于工具实现

**适用阶段**：Phase 1-3 均可

---

### 方案B：Dify（开源 Coze 替代）

**思路**：用 Dify 自建一个和 Coze 功能等价的平台。

**Dify 提供**：
- 可视化工作流编辑器（比 Coze 更灵活）
- 知识库（RAG）
- LLM 节点（支持 Claude、GPT 等）
- 代码节点（Python/JS）
- 定时任务
- Webhook 触发器
- 插件/工具市场
- API 发布

**与 Coze 对比**：

| 维度 | Coze | Dify |
|------|------|------|
| 部署 | SaaS（coze.cn） | 自托管（Docker/云服务器） |
| 开源 | 否 | 是（Apache 2.0） |
| 数据控制 | 数据在字节跳动服务器 | 数据在自己服务器 |
| 模型支持 | 字节系模型为主 | Claude、GPT、开源模型等 |
| 飞书集成 | 官方插件 | 需自建工具/Webhook |
| 费用 | 免费额度+付费 | 仅服务器成本 |
| 运维 | 零运维 | 需要维护服务器 |

**优点**：
- 功能与 Coze 几乎对等，替换成本低
- 开源可控，数据不出自己的服务器
- 工作流可视化，非技术人员也能编辑
- 模型选择自由（Claude、GPT、DeepSeek 等）
- 社区活跃，迭代快

**缺点**：
- 需要服务器（1台2C4G云服务器约 ¥100/月）
- 需要运维（部署、升级、备份）
- 飞书集成不是官方插件，需自行对接 API
- 仍然是一个额外的平台需要维护

**适用阶段**：Phase 3+（当工作流变得复杂，需要可视化管理和多人协作时）

---

### 方案C：n8n + Claude API

**思路**：n8n 做工作流编排，Claude API 做 LLM 推理。

**n8n 提供**：
- 强大的工作流编排（比 Coze/Dify 更专业）
- 400+ 集成节点（含飞书）
- 定时触发器、Webhook
- 代码节点
- 自托管

**优点**：
- 飞书有官方集成节点
- 工作流自动化能力最强
- 可编排的场景远超 AI 内容创作

**缺点**：
- AI 能力弱于 Coze/Dify（没有知识库、没有 LLM 节点生态）
- 需要搭 Claude API 才能做 LLM 推理
- 又多了一个平台需要维护
- 学习曲线高

**适用阶段**：不推荐。n8n 是个好工具，但我们的场景 AI 推理是核心，n8n 的 AI 能力是短板。

---

### 方案D：纯 Python 脚本 + 系统 Cron

**思路**：写 Python 脚本调用 Claude API + 飞书 API，用系统 cron 或 GitHub Actions 调度。

**优点**：
- 极致可控
- 零平台依赖
- 可集成任何 API
- 可以写单元测试

**缺点**：
- 开发工作量大（相当于从头写一个 Mini Coze）
- 没有可视化界面，修改 Prompt 需要改代码
- 没有知识库管理界面
- 错误处理、重试、日志都需要自己写
- 不适合非技术人员参与维护

**适用阶段**：不推荐用于初期。如果未来有专门的工程团队，可以考虑。

---

## 三、方案对比矩阵

| 维度 | A: Claude Code 原生 | B: Dify | C: n8n | D: Python 脚本 |
|:-----|:-------------------:|:-------:|:------:|:-------------:|
| **开发工作量** | 低（2-3天） | 中（1周） | 中-高（1-2周） | 高（2-3周） |
| **运维成本** | 零 | 服务器 ¥100/月 | 服务器 ¥100/月 | 服务器 ¥100/月 |
| **新平台学习** | 无 | 中 | 高 | 无（但要写代码） |
| **飞书卡片消息** | 降级为文本 | 需自建 | 原生支持 | 需自写 |
| **群聊 @Bot 交互** | 不支持 | 需自建 | 支持 | 需自写 |
| **知识库管理** | Git管理，始终最新 | 需手动同步 | 弱 | Git管理 |
| **可视化工作流** | 无 | 有 | 有 | 无 |
| **多模型支持** | Claude 模型 | 多种 | 需自接 | 需自接 |
| **团队协作** | 弱（都在CLI） | 好（Web UI） | 好（Web UI） | 弱 |
| **适合阶段** | Phase 1-2 | Phase 3+ | 不适合 | 不适合 |

---

## 四、推荐路径：方案A，逐步过渡

### 推荐 Phase 1 用 Claude Code 原生，Phase 3+ 评估 Dify

**理由**：

1. **Phase 1 的核心诉求是"选题AI化"**，不是"平台能力最大化"。Coze 工作流本质上是 6 个搜索 + 1 个 LLM 推理 + 1 个推送，这在 Claude Code 内用一个 Agent 就能完成。

2. **知识库同步是 Coze 的隐性成本**。`AI_Writing_Vault` 每更新一次，就要同步到 Coze 知识库。方案A直接读本地文件，永不过期。

3. **Phase 1-2 不需要群聊交互**。选题推送是单向的（Coze → 飞书群），不需要 @Bot 对话。飞书 Webhook 文本消息足够。

4. **先跑通再平台化**。如果 Phase 1 用 Claude Code 原生跑通了，后续评估 Dify 时有真实的业务需求做参照，不会过度设计。

5. **CronCreate 的实验性质**。先用 CronCreate 验证定时选题的价值，如果确实每天都需要，后续可以升级到更可靠的调度方式。

### 何时切换到 Dify？

当以下条件同时满足时，考虑从方案A 迁移到方案B：

- [ ] 选题工作流稳定运行超过 1 个月，每日产出可靠
- [ ] 团队有非技术人员需要参与工作流编辑（如市场同事要调整评分规则）
- [ ] 需要群聊 @Bot 交互（老板想在群里 @ 选题助手）
- [ ] 需要飞书卡片消息的按钮交互（"选这个写""换一批"）
- [ ] 有专人能维护 Dify 服务器
- [ ] 工作流节点数 > 10，可视化管理的价值凸显

---

## 五、Claude Code 原生方案具体设计

### 5.1 整体架构

```
┌─ CronCreate (durable) ──────────────────────────┐
│  工作日 9:27 + 14:13                              │
│  触发 Prompt: "执行模力指数选题扫描"               │
└────────────────────┬────────────────────────────┘
                     ↓
┌─ Agent: topic-scout ────────────────────────────┐
│                                                    │
│  1. 并行搜索 (WebSearch × 6)                       │
│     - 微博热搜 AI 品牌营销                         │
│     - 知乎 AI 营销 数字化转型                      │
│     - 百度 企业服务 AI 科技                        │
│     - 36氪/虎嗅 AI创投 大模型                      │
│     - 微信搜一搜 GEO 品牌监测                      │
│     - 小红书 AI工具 品牌运营                       │
│                                                    │
│  2. 合并去重 (Bash: python agent/scripts/dedup.py) │
│                                                    │
│  3. 加载知识库 (Read AI_Writing_Vault/)             │
│     - 品牌声音与读者定位                            │
│     - GEO写作专项                                  │
│     - 热点事件型文章                                │
│     - 文章Brief模板                                │
│     - 近期已发文章 (codexarticles/ 最近5篇)         │
│                                                    │
│  4. 规则评估 + 三维打分 (Agent 推理)                │
│     硬过滤 → 三维打分 → 分级 → 深度分析            │
│                                                    │
│  5. 生成Brief (Write: outputs/topic-briefs/)       │
│     YYYY-MM-DD-topic-brief.md                     │
│                                                    │
│  6. 飞书推送 (Bash: curl 飞书 webhook)             │
│     推送摘要 + Brief 文件路径                      │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 5.2 飞书推送降级方案

Coze 飞书卡片消息 → Claude Code 飞书 Webhook 文本消息：

```
飞书自定义机器人 Webhook：
https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxx

消息格式（Markdown）：
====================================
📰 模力指数选题日报
2026-06-24（周二）

扫描 7 平台：15 条候选 → 通过 5 条
🔥 推荐写（≥12分）：3 条
💾 可储备（9-11分）：2 条

--- 推荐选题 ---

#1 豆包2.1 Pro发布对GEO的影响
评分：13/15（价值5 差异4 传播4）
类型：热点解读 | 读者：服务商负责人
核心矛盾：模型更新了品牌引用逻辑变了
风险：需核验2.1具体能力变化
详情：outputs/topic-briefs/2026-06-24-topic-brief.md

#2 ...
#3 ...

⏰ 下次扫描：明天 9:27
====================================
```

> 注意：飞书自定义机器人发送的是纯文本/Markdown，不支持卡片按钮。交互方式降级为"群内回复文字确认"。

### 5.3 手动触发方式

```bash
# 在 Claude Code 中：
> 执行选题扫描

# 或直接调用 Agent：
> 用 topic-scout agent 扫描今天的选题
```

### 5.4 文件结构

```
agent/
├── projectplan/          # 设计文档（不变）
│   ├── 01-architecture-overview.md
│   ├── 02-evolution-roadmap.md
│   ├── 03-coze-bot-design.md
│   ├── 04-agent-worker-taxonomy.md
│   ├── 05-coze-step-by-step-guide.md
│   └── 06-coze-replacement-analysis.md  ← 新增
├── scripts/
│   └── dedup.py          # 搜索结果合并去重脚本
├── prompts/
│   └── topic-scout.md    # 选题 Agent 的 System Prompt
└── outputs/
    └── topic-briefs/     # 生成的选题 Brief
        └── YYYY-MM-DD-topic-brief.md

outputs/
└── topic-briefs/         # 或者放这里，与现有 outputs 对齐
```

### 5.5 Topic Scout Agent Prompt 骨架

```
你是模力指数公众号的选题编辑 Agent。

## 任务
扫描中国互联网热点，按知识库规则评估选题，生成标准化选题简报并推送飞书。

## 每次执行的步骤
1. 搜索6个平台的热点（WebSearch）
2. 合并去重（Python脚本）
3. 阅读知识库文件（Read）：
   - AI_Writing_Vault/10_核心规则/品牌声音与读者定位.md
   - AI_Writing_Vault/20_专项流程/GEO写作专项.md
   - AI_Writing_Vault/20_专项流程/热点事件型文章.md
   - AI_Writing_Vault/30_模板/文章Brief模板.md
   - codexarticles/ 最近5篇文章
4. 按三维打分体系评估每条候选
5. 生成 Markdown Brief 写入 outputs/topic-briefs/
6. 通过 curl 飞书 Webhook 推送摘要

## 评估规则（嵌入，与03-coze-bot-design.md一致）
...（硬过滤 + 三维打分 + 分级 + 19字段Brief）...

## 输出要求
- 推荐选题 >= 12分，最多 {{count}} 条
- Brief 包含完整19字段
- 飞书推送包含评分摘要和文件路径
```

---

## 六、下一步行动（更新后）

原计划（依赖 Coze）：

1. [x] ~~在 Coze 平台创建 Bot~~
2. [x] ~~上传知识库文件~~
3. [ ] ~~搭建工作流（6个节点）~~
4. [ ] ~~配置飞书机器人~~
5. [ ] ~~测试定时扫描 + 手动触发~~

新计划（Claude Code 原生）：

1. [ ] 创建 `agent/prompts/topic-scout.md` — 选题 Agent Prompt
2. [ ] 创建 `agent/scripts/dedup.py` — 合并去重脚本
3. [ ] 在 Claude Code 中手动测试一次选题扫描（验证输出质量）
4. [ ] 配置飞书自定义机器人 Webhook（群聊添加机器人，获取 webhook URL）
5. [ ] 创建 `CronCreate` 定时任务（工作日 9:27 + 14:13）
6. [ ] 连续观察 5 个工作日，对比 AI 选题 vs 人工选题的质量
7. [ ] 调优评分 Prompt、搜索关键词、推送格式
8. [ ] 决定是否保持 Claude Code 原生 or 迁移到 Dify

---

## 七、讨论待定事项

以下问题需要在讨论中确认：

### 7.1 WebSearch 覆盖范围是否足够？

Claude Code 的 WebSearch 工具是否能覆盖微博、知乎、百度、36氪、微信、小红书的内容？如果覆盖不足，是否需要补充 RSS 订阅、API 调用等数据源？

> **初步判断**：WebSearch 主要是通用搜索引擎搜索，对中文社交平台内容覆盖可能有限。可以考虑：
> - 用 `WebFetch` 直接抓取微博热搜榜 API、知乎热榜 API
> - 用 `Bash curl` 调用新榜、搜狗微信等第三方数据接口
> - 接受 Phase 1 覆盖不完美，先跑通流程

### 7.2 飞书卡片消息是否不可替代？

如果团队强烈需要卡片消息的按钮交互（"选这个写" / "查看详情"），那么 Claude Code 原生方案需要增加飞书卡片 API 的调用能力（用 curl 构造卡片 JSON 发飞书 API），这在技术上可行但需要额外的开发工作。

### 7.3 CronCreate 的可靠性？

CronCreate durable 需要 Claude Code 进程持续运行。如果机器休眠或 Claude Code 退出，定时任务不会触发。是否需要考虑：
- 使用 GitHub Actions 做外部调度（触发 Claude Code CLI）
- 使用系统计划任务（Windows Task Scheduler）做备份触发器

### 7.4 知识库文件是否太大？

`AI_Writing_Vault/` 的文件直接 Read 到 Agent 上下文中。如果文件总大小超过上下文窗口，需要考虑：
- 只加载核心规则文件（非全部）
- 用 Grep 精准提取相关段落
- 实测各模型上下文限制

### 7.5 Coze 知识库文档是否保留？

`03-coze-bot-design.md` 中关于知识库同步的部分是否需要修改或标注为 "如果未来切换到 Coze/Dify 则使用"？

---

## 八、总结

| 结论 | 内容 |
|------|------|
| **推荐方案** | Claude Code 原生（方案A），Phase 1 直接用 |
| **备选方案** | Dify（方案B），Phase 3+ 需要可视化和团队协作时评估 |
| **立即行动** | 创建 topic-scout Agent Prompt + dedup 脚本，手动测试一次 |
| **关键风险** | WebSearch 中文社交平台覆盖率 + CronCreate 可靠性 |
| **可回退** | 如果 Claude Code 原生体验不好，随时可以回到 Coze（Coze Bot 设计文档保留） |
