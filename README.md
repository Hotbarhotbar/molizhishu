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
