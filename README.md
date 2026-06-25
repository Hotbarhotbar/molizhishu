# molizhishu agent

模力指数内容工作流原型仓库。当前已实现「GEO热点新闻抓取与选题生成」离线 MVP：

1. 六类选题依据采集占位
2. 空结果容错
3. 内容清洗
4. 标题去重
5. 简单 GEO 相关性评分
6. 推荐 / 储备 / 放弃分层
7. Markdown 日报输出
8. 可选飞书 webhook 推送

## 运行

全空输入验证：

```powershell
python scripts\run_topic_scout_mvp.py --fixture empty
```

示例输入验证：

```powershell
python scripts\run_topic_scout_mvp.py --fixture example
```

使用本地 JSON 输入：

```powershell
python scripts\run_topic_scout_mvp.py --fixture file --input-json path\to\search_results.json
```

默认输出：

```text
outputs/topic-briefs/YYYY-MM-DD-topic-brief.md
```

没有飞书 webhook 时只保存 Markdown，不报错。

## 飞书推送

推荐把 webhook 放在当前终端环境变量里，不要写入代码或提交到仓库：

```powershell
$env:FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/你的-webhook"
python scripts\run_topic_scout_mvp.py --fixture example
```

也可以只在单次运行时传入：

```powershell
python scripts\run_topic_scout_mvp.py --fixture example --feishu-webhook "https://open.feishu.cn/open-apis/bot/v2/hook/你的-webhook"
```

脚本会先保存 Markdown，再尝试推送；推送失败不会中断日报生成。

飞书消息只推送可读摘要：候选数量、推荐/储备/放弃数量、最多 3 条推荐选题和本地 Markdown 路径。完整 Brief、六类采集复盘和风险审核细节都保存在 Markdown 日报里。

## 模型 API Key 接口

脚本默认不调用模型，完全可以离线运行。需要用模型增强选题标题、角度和风险提示时，启用 OpenAI-compatible 接口：

```powershell
$env:USE_LLM = "1"
$env:LLM_PROVIDER = "deepseek"
$env:LLM_API_KEY = "你的模型APIKey"
$env:LLM_MODEL = "deepseek-chat"
python scripts\run_topic_scout_mvp.py --fixture example
```

支持的 provider 预设：

| provider | 默认 Base URL | 默认 key 环境变量 | 默认模型 |
|---|---|---|---|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `deepseek` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | `qwen-plus` |
| `moonshot` | `https://api.moonshot.cn/v1` | `MOONSHOT_API_KEY` | `moonshot-v1-8k` |
| `custom` | 读取 `LLM_BASE_URL` | `LLM_API_KEY` | 读取 `LLM_MODEL` |

自定义 OpenAI-compatible 服务：

```powershell
$env:USE_LLM = "1"
$env:LLM_PROVIDER = "custom"
$env:LLM_BASE_URL = "https://your-model-service.example.com/v1"
$env:LLM_API_KEY = "你的模型APIKey"
$env:LLM_MODEL = "your-model-name"
python scripts\run_topic_scout_mvp.py --fixture file --input-json path\to\search_results.json
```

模型调用只做增强，不做硬依赖。API Key 缺失、接口超时或返回格式不对时，脚本会记录 warning，并回退到规则生成结果继续保存日报。
