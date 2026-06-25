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

飞书消息只推送群内可读摘要：候选数量、推荐/储备/放弃数量、最多 3 条推荐选题、事实依据、产品承接和风险提示。Markdown 日报保存在运行机器本地，只做归档，不作为群成员打开入口。

如果需要群成员打开完整文档，推荐三种升级路线：

1. **飞书云文档**：接飞书开放平台文档 API，运行后自动创建云文档，再把文档链接推到群里。最适合团队协作，但需要配置飞书应用凭证。
2. **团队可访问网页**：把日报发布到内网、对象存储、GitHub Pages 或其他静态站点，再推 URL。最简单稳定，但需要一个可访问的发布位置。
3. **飞书文件上传**：用飞书文件/素材接口上传 Markdown 或 PDF，再发到群里。比 webhook 复杂，需要应用 token，不适合只靠自定义机器人 webhook 完成。

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
