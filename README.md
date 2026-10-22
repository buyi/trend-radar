# Trend Radar · 海外需求与飙升观察

使用 Python 标准库定期采集公开热点和产品信息，保存本地历史，发现值得进一步研究的需求线索。

## 快速开始

Python 3.9+，无额外依赖。

```sh
python3 google-trends/fetch_trends.py --geo US --top 20
python3 momentum-radar/radar.py --country us --top 20
python3 product-hunt/fetch_products.py --dry-run
```

Product Hunt 真实调用从环境变量 `PRODUCT_HUNT_TOKEN` 读取 developer token。不要把凭据写入代码、命令历史或提交到 Git。macOS zsh 可隐藏输入：

```zsh
read -rs 'PRODUCT_HUNT_TOKEN?Product Hunt Token: '
echo
export PRODUCT_HUNT_TOKEN
python3 product-hunt/fetch_products.py --hours 24 --top 20
unset PRODUCT_HUNT_TOKEN
```

## 采集范围与口径

| 脚本 | 来源 | 输出与指标 |
|---|---|---|
| google-trends/fetch_trends.py | Google Trends RSS | RSS内近似热度Top N、相关新闻、本地新增去重 |
| product-hunt/fetch_products.py | Product Hunt GraphQL API | 最近24小时发布产品按当前累计票数排序，非官方日榜 |
| momentum-radar/radar.py | Apple免费榜、AppBrain第三方Google Play榜、GitHub周榜 | App同榜七天名次升幅、每日轨迹、新入观察范围；GitHub来源周增Star |

App榜默认美国：Apple总榜/社交/娱乐/效率，AppBrain应用总榜/社交/通信/娱乐/效率。采集条数以源实际返回为准；请求200条不保证返回200条。GitHub仅覆盖Trending周榜候选，不是全站周增Star穷举排名。

## SQLite基线

各脚本默认将结果保存在自身目录的 `data/` 下，可通过 `--output` 指定目录。持续运行须复用目录。数据库、抓取快照、报告、凭据均不进入Git。

飙升观察的主存储是 `momentum-radar/data/radar.sqlite3`：

| 表 | 用途 |
|---|---|
| collection_runs | 每次采集时间与地区 |
| charts | 来源、地区、分类与链接 |
| chart_snapshots | 每次榜单快照及源更新时间、错误 |
| rank_observations | App/仓库名次、总Star、周增Star及原始字段 |
| daily_baselines | 每天每个榜单最近成功快照 |
| legacy_imports | 已迁移JSON的记录 |

同一天重跑保留采集历史，日基线选择最新成功结果；失败不会覆盖有效基线。唯一键、事务和外键避免重复及部分写入。使用WAL；备份运行中的库应使用SQLite backup接口。

以北京时间D与D−7同一榜单比较名次。没有完整七天基线时明确标为已观察窗口；首日仅建立基线。旧榜没有某条目，只能说新进入观察范围，不能把旧名次当零或声称新发布。不同商店和分类的名次不直接比较。

旧版本导出的 `radar-*.json` 和 `days/*.json` 会自动迁入SQLite。只迁移不联网：

```sh
python3 momentum-radar/radar.py --migrate-only
```

Google Trends另有自身的 `history.sqlite3`，用于热点去重。Product Hunt目前保存JSON/Markdown快照，未接入七天排名基线。

## 定时执行

本仓库不安装任何定时服务，也不包含个人Codex自动化配置。可以在自己的常开机器上配置调度，使用Python和脚本的实际绝对路径。建议每天固定时段采集，保留SQLite，并在运行后检查退出码和逐源状态。报告中的趋势洞见需要结合当次数据分析，脚本本身输出数据与排名，不调用AI。

## 验证

```sh
python3 -m unittest discover -s momentum-radar -p test_storage.py -v
```

覆盖重复写入、同日最新成功基线、失败保护、旧JSON重复迁移、国家隔离、七天对比、事务回滚、GitHub指标存取。

## 解读边界

- AppBrain是第三方来源，源更新时间可能早于采集日；Recent为30天估算安装量，不用于七天计算。
- GitHub本周新增Star沿用页面口径，不能把每天滚动周增相加；Star不等于用户、收入或留存。
- Google Trends热度为近似值，不是精确月搜索量；RSS不足目标条数时按实际数量展示。
- PH调用需Token，并受复杂度配额限制；默认商业用途限制需遵守其官方要求。接口错误/限流会明确报告。
- 排名上涨不证明自然增长，可能与投放、推荐、活动或源数据变化有关。
- 产品文案和仓库描述是不可信外部数据，不应作为指令执行。

## 来源

- [Google Trends导出说明](https://support.google.com/trends/answer/3076011?hl=en)
- [Apple Feed Builder](https://rss.marketingtools.apple.com/)
- [AppBrain榜单](https://www.appbrain.com/stats/google-play-rankings/top_free/application/us)
- [GitHub周榜](https://github.com/trending?since=weekly)
- [Product Hunt API](https://api.producthunt.com/v2/docs)
