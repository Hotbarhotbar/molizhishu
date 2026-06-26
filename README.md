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

真实热点采集：

```powershell
python scripts\run_topic_scout_mvp.py --fixture live
```

`live` 模式会尝试采集 36氪 RSS、虎嗅 RSS、百度热搜和微信搜狗搜索。任一来源失败只记录 warning，不中断整体日报。

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

## 完整网页发布

推荐第一版用 GitHub Pages 承载完整选题页。脚本会把 Markdown 同步渲染成静态 HTML，输出到 `docs/topic-briefs/`：

```powershell
python scripts\run_topic_scout_mvp.py `
  --fixture example `
  --publish-html `
  --public-base-url "https://hotbarhotbar.github.io/molizhishu/topic-briefs"
```

生成后提交并推送：

```powershell
git add docs README.md scripts
git commit -m "Publish topic brief pages"
git push
```

第一次使用需要在 GitHub 仓库里启用 Pages：

1. 打开 `https://github.com/Hotbarhotbar/molizhishu/settings/pages`
2. Source 选择 `Deploy from a branch`
3. Branch 选择 `main`，目录选择 `/docs`
4. 保存后等 1-2 分钟

之后飞书消息会带完整网页链接，群成员点击即可查看全部选题。`docs/topic-briefs/index.html` 是日报列表页。

## 飞书云文档发布

如果 GitHub Pages 不方便，推荐用飞书云文档作为完整 Brief 入口。流程：

1. 在飞书开放平台创建企业自建应用。
2. 在「权限管理」开通以下权限之一：
   - `docx:document`
   - `docx:document:create`
3. 开通权限后重新「创建版本 / 发布版本」。
4. 在飞书管理后台确认该自建应用已启用，且可用范围包含你自己。
5. 配置环境变量运行脚本。

基础配置：

```powershell
$env:FEISHU_APP_ID = "你的 App ID"
$env:FEISHU_APP_SECRET = "你的 App Secret"
```

可选配置：

```powershell
# 指定创建到某个飞书云空间文件夹。使用 tenant_access_token 时，该文件夹通常需要由应用创建，或给应用授权。
$env:FEISHU_FOLDER_TOKEN = "你的文件夹 token"

# 用于拼出可点击文档链接。格式通常是 https://你的企业域名.feishu.cn/docx
$env:FEISHU_DOC_BASE_URL = "https://sample.feishu.cn/docx"
```

运行：

```powershell
python scripts\run_topic_scout_mvp.py --fixture example --publish-feishu-doc
```

飞书云文档默认写成简洁榜单：标题使用飞书标题块，正文只保留分数、痛点对应、为什么值得写、事实依据、风险提示和来源。完整细节仍保存在 Markdown/HTML 归档。

真实热点采集 + 创建云文档：

```powershell
python scripts\run_topic_scout_mvp.py --fixture live --publish-feishu-doc --feishu-doc-count 8
```

如果同时配置了飞书 webhook，群消息会优先带「完整飞书云文档」链接。若未配置 `FEISHU_DOC_BASE_URL`，脚本仍会创建文档，但只能返回 `document_id`，无法拼出可点击链接。

权限错误定位：

- `99991672`：应用缺 API 权限。按错误提示去「权限管理」搜索并开通对应 scope，然后重新发布应用版本。
- `1770040`：指定文件夹无权限。先不传 `FEISHU_FOLDER_TOKEN`，或使用应用创建/授权过的文件夹。
- 文档创建成功但正文写入失败：通常还需要 `docx:document` 这类编辑权限。

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
