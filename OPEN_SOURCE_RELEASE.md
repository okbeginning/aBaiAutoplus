# 开源前安全审计与发布清单

> 本文件用于开源前自查。**处理完成后可删除本文件**，或在清理后保留作为发布记录。
> 文档内不写完整密钥值，只给「文件:行号」定位，便于安全公开。

审计时间：2026-05-31
审计范围：git 已跟踪文件 + 源码硬编码扫描

---

## 风险分级总览

| 级别 | 类型 | 数量 | 处置 |
|---|---|---|---|
| 🔴 P0 | 真实账号凭证已进 git | 3 个文件 | 立即删除 + 重写历史 + 轮换 |
| 🔴 P0 | 调试 dump（含第三方实时 cookie/PII） | 13 个 txt | 立即删除 + 重写历史 |
| 🟠 P1 | 源码写死「作者自有」付费 API key | 2 处 | 改为 env 读取 + 吊销旧 key |
| 🟡 P2 | 源码写死第三方 APK 逆向密钥 | 3 处 | 评估法律/ToS 风险 |
| 🟢 P3 | 第三方前端公开常量 | 4 处 | 可保留 |
| 🟡 P2 | 不安全默认配置 | 4 项 | 文档提醒 + 启动校验 |

---

## 🔴 P0-1 真实账号凭证（已被 git 跟踪）

这些不是占位符，是**可直接登录使用的真实凭证**。开源即泄露。

| 文件 | 泄露内容 |
|---|---|
| `acc.json` | 81 个 ChatGPT 账号完整导出：明文密码、access_token / session_token（JWT）、完整登录 cookies（`cf_clearance` / `__Secure-next-auth.session-token` 等）、`pay.openai.com` 的 `cs_live_` 支付链接、出口代理 `***@gate-jp.kookeey.info:1000` |
| `acc81.json` | 单个 ChatGPT 账号，内容同上 |
| `platforms/gopay-deploy/config/gopay_worker_accounts.json` | 8 个印尼 GoPay 账号：手机号、PIN（明文 `147258`）、`access_token` / `refresh_token`（JWE）、`customer_id` |

> ⚠️ 仅删文件不够：这些已在 git 历史里，必须重写历史（见下方「清理步骤」），并**立即轮换/作废**对应账号。

---

## 🔴 P0-2 调试 dump 文件（已被 git 跟踪）

抓包/调试时 dump 的中间文件，含第三方平台实时 cookie、税务地址等 PII：

| 文件 | 泄露内容 |
|---|---|
| `s_inspect.txt` `p_inspect.txt` `tax.txt` | Stripe `pk_live_` publishable key、checkout session id、真实税务地址（街道/城市/邮编） |
| `otp_headers.txt` `logger.txt` `tsrce_origin.txt` | PayPal `datadome` / `ts` / `ts_c` / `x-pp-s` cookie、`ec_token` / `ba_token` |
| `otp_bodies.txt` `otp_responses.txt` `otp_nonce.txt` `otp_cookies.txt` | OTP 子链请求/响应 dump |
| `har_entries_otp_range.txt` `har_otp_challenge_req.txt` | HAR 抽取片段 |
| `task_events.txt` | 运行日志：出口代理地址、账号邮箱、`payment_method_id` |
| `progress.txt` `pytest_out.txt` | 开发进度笔记 / 测试输出（非敏感，但属调试残留，建议一并清掉） |

---

## 🟠 P1 源码写死的「作者自有」付费 API key

下面两个是作者自己的付费接码平台 key，被写死成默认 fallback。开源后任何人都能盗刷你的余额。

| 位置 | 变量 | 处置 |
|---|---|---|
| `platforms/gopay/sms_channel.py:50` | `SMSPOOL_DEFAULT_API_KEY = "i84C…Zh"` | 改为 `os.environ.get(...)`，默认空串；去 SMSPool 后台吊销重置 |
| `platforms/gopay/sms_channel.py:284` | `SMSBOWER_DEFAULT_API_KEY = "4vX4…sY"` | 改为 env 读取；去 SMSBower 吊销重置 |

建议改法（保持现有「空则兜底」逻辑，只是兜底值来自环境变量）：

```python
SMSPOOL_DEFAULT_API_KEY = os.environ.get("OPAI_SMSPOOL_API_KEY", "")
SMSBOWER_DEFAULT_API_KEY = os.environ.get("OPAI_SMSBOWER_API_KEY", "")
```

调用方已是 `str(api_key or "").strip() or SMSPOOL_DEFAULT_API_KEY`，改成空串后逻辑不变，只是未配置时会走到「key 为空」的报错路径，符合开源预期。

---

## 🟡 P2 源码写死的第三方 APK 逆向密钥

这些不是作者的密钥，是从 GoJek 安卓客户端逆向出来的固定常量。技术上「全网同一份」，但放进开源仓库有 **ToS / 法律风险**，且字面上是 `SECRET`。

| 位置 | 变量 |
|---|---|
| `platforms/gopay-deploy/app/src/opai/core/gojek_client.py:57` | `CLIENT_SECRET = "pGwQ…lb"` |
| 同文件 `:728` | `_GOJEK_API_KEY = "f389…b581"` |
| 同文件 `:60` `:932` `:1307` | `ORIGINAL_D1` 证书指纹、`LOGIN_PIN_CLIENT_ID`、`PIN_CLIENT_ID` 等固定 id |

处置建议（任选）：
- 移到 env / 配置文件，默认空串，README 说明「需自行从客户端抓取」；
- 或保留但在 README 明确声明来源与免责（与现有「仅供学习研究」免责一致）。

---

## 🟢 P3 第三方前端公开常量（可保留）

这些设计上就是浏览器可见的公开标识，不算泄露，列出供参考：

| 位置 | 变量 | 说明 |
|---|---|---|
| `platforms/cerebras/core.py:18` | `STYTCH_PUBLIC_TOKEN` | Stytch public token，前端公开 |
| `platforms/tavily/core.py:5` | `AUTH0_CLIENT_ID` | Auth0 client id，前端公开 |
| `platforms/grok/core.py:9` | `TURNSTILE_SITEKEY` | Cloudflare Turnstile sitekey，公开 |
| `platforms/cursor/core.py:8-10` | `ACTION_*` | Next.js server action 哈希，公开 |

---

## 🟡 P2 不安全的默认配置（customer_portal_api）

占位符本身不算泄露，但默认值不安全，需在文档强调「生产必改」，最好启动时校验。

| 位置 | 配置 | 默认值 | 建议 |
|---|---|---|---|
| `customer_portal_api/app/config.py:9` | `jwt_secret` | `change-me-in-production` | 启动时若仍为默认值则告警/拒绝启动 |
| `customer_portal_api/app/config.py:13` | `seed_admin_password` | `admin123456` | README 强调首次登录后立即改密 |
| `customer_portal_api/app/config.py:16` | `cors_origins` | `*` | 生产收敛到具体域名 |
| `customer_portal_api/.env.example:6` | `PORTAL_ADMIN_PASSWORD` | `admin123456` | example 可保留占位，但加注释提醒 |

---

## 未被 git 跟踪、但本地存在的敏感文件（确认即可）

这些当前没进 git（已被 `.gitignore` 覆盖），开源不会泄露，但要确认它们**从未被历史 commit 过**：

- `account_manager.db`（主数据库，含全部账号凭证）— 规则 `*.db` ✅
- `.env` — 规则 `.env` ✅（当前内容无敏感信息）

确认命令：`git log --all --oneline -- account_manager.db`（无输出 = 从未提交）

---

## 清理步骤

### 1. 从 git 移除并删除工作区文件

```powershell
# P0 真实凭证
git rm acc.json acc81.json
git rm platforms/gopay-deploy/config/gopay_worker_accounts.json

# P0 调试 dump
git rm s_inspect.txt p_inspect.txt tax.txt otp_headers.txt logger.txt tsrce_origin.txt
git rm otp_bodies.txt otp_responses.txt otp_nonce.txt otp_cookies.txt
git rm har_entries_otp_range.txt har_otp_challenge_req.txt task_events.txt
git rm progress.txt pytest_out.txt
```

### 2. 加固 .gitignore（追加）

```gitignore
# 账号导出 / 真实凭证
acc*.json
**/gopay_worker_accounts.json

# 抓包 / 调试 dump
*_inspect.txt
otp_*.txt
har_*.txt
logger.txt
tsrce_origin.txt
task_events.txt
tax.txt
progress.txt
pytest_out.txt
tools/captures/
```

### 3. 改源码 P1（见上方代码块）

### 4. 重写 git 历史（因为上述文件已被提交过）

> ⚠️ **不可逆 + 改写公共历史**。如果仓库还没 push 到公开远端，是清理的最佳时机。

推荐用 `git filter-repo`：

```powershell
pip install git-filter-repo
git filter-repo --invert-paths `
  --path acc.json --path acc81.json `
  --path platforms/gopay-deploy/config/gopay_worker_accounts.json `
  --path s_inspect.txt --path p_inspect.txt --path tax.txt `
  --path otp_headers.txt --path otp_bodies.txt --path otp_responses.txt `
  --path otp_nonce.txt --path otp_cookies.txt --path logger.txt `
  --path tsrce_origin.txt --path task_events.txt `
  --path har_entries_otp_range.txt --path har_otp_challenge_req.txt `
  --path progress.txt --path pytest_out.txt
```

### 5. 轮换/作废所有已泄露凭证（最重要，删文件挡不住已被抓走的数据）

- [ ] `acc.json` / `acc81.json` 里的 ChatGPT 账号：改密 + 注销会话
- [ ] GoPay worker 账号：作废 token / 改 PIN
- [ ] SMSPool API key：后台 reset
- [ ] SMSBower API key：后台 reset
- [ ] 代理 `gate-jp.kookeey.info` 凭证：更换
- [ ] Stripe `pk_live_`：publishable key 影响小，但确认无 `sk_` 泄露

---

## 开源标配文件状态

| 文件 | 状态 |
|---|---|
| `LICENSE`（AGPL-3.0） | ✅ 已有 |
| `README.md` / `README_en.md` / `README_vi.md` | ✅ 已有，内容完善 |
| `CONTRIBUTING.md` | ✅ 已有 |
| `.github/ISSUE_TEMPLATE/` | ✅ 已有 |
| `customer_portal_api/.env.example` | ✅ 已有 |
| 根项目 `.env.example` | ❌ 缺失（建议补，列出 `BIT_PROFILE_ID` / `OPAI_SMSPOOL_API_KEY` 等可配项） |
| `SECURITY.md` | ❌ 缺失（GitHub 推荐，建议补漏洞上报方式） |

---

## 发布前最终检查清单

- [ ] P0 文件已 `git rm` 且工作区已删
- [ ] `.gitignore` 已加固
- [ ] P1 源码改为 env 读取
- [ ] git 历史已重写，`git log --all` 确认敏感文件消失
- [ ] 所有泄露凭证已轮换
- [ ] `account_manager.db` 确认从未进历史
- [ ] 补 `SECURITY.md` 与根 `.env.example`（可选）
