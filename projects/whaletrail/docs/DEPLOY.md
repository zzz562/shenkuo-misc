# Deploy — Mac mini 运行与运维

> Mac mini 是运行/部署机。本文档只覆盖 whaletrail 相关服务；gwht 不依赖 gvalar 手册。

## 连接

```bash
ssh macmini        # Thunderbolt → VPS fallback
ssh macmini-fwd    # Thunderbolt + 端口转发
ssh macmini-remote # 强制走 VPS
```

| 端点 | IP |
|------|-----|
| MacBook Thunderbolt | `169.254.66.46` |
| Mac mini Thunderbolt | `169.254.230.133` |
| VPS 跳板 | `139.224.244.214:2222` |

## 代码部署

```bash
cd ~/Projects/whaletrail-lab
git pull origin main
```

若 Mac mini 无法访问 GitHub，改用 rsync 从 MacBook 同步：

```bash
rsync -avz ~/github_code/whaletrail-lab/ macmini:~/Projects/whaletrail-lab/ \
  --exclude .venv --exclude data_cache --exclude results --exclude logs
```

## 端口转发（MacBook 访问 Mac mini 服务）

```bash
ssh -L 8766:localhost:8766 -L 18789:localhost:18789 -L 11434:localhost:11434 macmini
```

## launchd 服务

| Label | 用途 |
|-------|------|
| `ai.whaletrail-live` | paper trading 实时扫描 |
| `ai.openclaw.gateway` | OpenClaw AI Agent 网关 |
| `homebrew.mxcl.ollama` | 本地 LLM（qwen3:4b） |
| `com.zeph.reverse-tunnel` | SSH 反向隧道 → VPS |

## Cron（OpenClaw）

```bash
openclaw cron list
openclaw cron run whaletrail-daily       # 手动触发日报
openclaw cron run whaletrail-sentiment   # 手动触发情绪扫描
```

| 任务 | 调度 | 说明 |
|------|------|------|
| `whaletrail-daily` | 工作日 08:30 CST | `daily-report.sh gold_sma GLD` → Telegram |
| `whaletrail-sentiment` | 每日 09:00 CST | X KOL 情绪扫描 → Telegram |
| `whaletrail-ashare` | 工作日 15:30 CST | A股低频率 paper（`ashare-paper.py`）→ Telegram |

## 日志

```bash
tail -f ~/Projects/whaletrail-lab/projects/whaletrail/logs/paper-live.log
tail -f ~/Projects/whaletrail-lab/projects/whaletrail/logs/paper-live.err
tail -f ~/.openclaw/logs/gateway.err.log
```

## 排障

**whaletrail-live 异常：**

```bash
launchctl list | grep whaletrail-live
launchctl print gui/$(id -u)/ai.whaletrail-live
# 重启
launchctl bootout gui/$(id -u)/ai.whaletrail-live
launchctl bootstrap gui/$(id -u)/~/Library/LaunchAgents/ai.whaletrail-live.plist
```

**venv 路径异常：**

```bash
cd ~/Projects/whaletrail-lab/projects/whaletrail
.venv/bin/python -c "import sys; print(sys.executable)"
# 如果路径不对，重建：
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**OpenClaw Gateway 起不来（PID=-1）：**

```bash
ssh macmini 'export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm use 24 > /dev/null 2>&1 && export PATH="$(dirname $(which node)):/opt/homebrew/bin:$PATH" && openclaw doctor --fix'
```

**xAI 认证过期：**

```bash
ssh macmini 'export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && nvm use 24 && export PATH="$(dirname $(which node)):/opt/homebrew/bin:$PATH" && openclaw models auth login --provider xai'
```

## VPS 反向隧道检查

```bash
ssh aliyun-vps 'ss -tlnp | grep 2222'
# 无输出 = mini 隧道断了，到 mini 上重启 reverse-tunnel
```
