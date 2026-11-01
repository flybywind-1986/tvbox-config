# tvbox-config

把一堆会失效的 TVBox 源，变成一个**永远不变**的地址。

## 它做什么

1. 读 `sources.txt` 里你列的 N 个上游配置地址
2. 每 6 小时（GitHub Actions）抓一遍，验证：HTTP 200 + 是合法 JSON + 含 `sites` 或 `urls`
3. 把活着的合并成一个**多仓** `config.json`
4. 自动 commit，生成 `report.md` 记录谁死了、为什么

你的电视里只填一个地址：

```
https://raw.githubusercontent.com/<你的用户名>/tvbox-config/main/config.json
```

上游换了域名、挂了、跑路了，你的地址都不用改——TV 每次启动都会重新拉这个地址。

## 部署（5 分钟）

1. GitHub 上新建仓库 `tvbox-config`（Public，否则 raw 链接要 token）
2. 把这四个东西传上去：`sources.txt`、`scripts/build_config.py`、`.github/workflows/update.yml`、`README.md`
3. 编辑 `sources.txt`，填你要用的上游地址
4. 仓库 → Actions → 允许 workflows → 点 `update-tvbox-config` → Run workflow
5. 跑完看 `report.md`，然后用 raw 地址在电视上配置

## 本地试跑

```powershell
python scripts/build_config.py            # 真跑
python scripts/build_config.py --selftest # 不联网自测
```

只用标准库，不用 pip 装东西。

## 电视端怎么填

FongMi / TVBox：设置 → 配置地址 → 粘贴上面的 raw 地址 → 确定 → 回首页。
多仓模式下会看到若干个"仓"，每个仓里才是具体站点；某个仓挂了，别的仓还能用。

> 加速：国内直连 `raw.githubusercontent.com` 经常失败，可以把地址换成
> `https://cdn.jsdelivr.net/gh/<用户名>/tvbox-config@main/config.json`
> （jsDelivr 缓存约 12 小时，介意时效就用 raw）。
