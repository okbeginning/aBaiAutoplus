# PayPal Checkout 协议反推笔记

来源：`tools/captures/checkout-20260523-160436-04xg0pylps_edu.hsxhome.com.har`（846 个请求，77MB）。本文档把 PayPal 部分的关键端点按调用顺序罗列出来，作为后续 `paypal_http.py` / `proto_stage_paypal_*` 实现的契约。

> **重要结论 (2026-05-23 重新核对成功 HAR 后修订)**：
>
> 这条 HAR **是完整成功付款的链路**，使用的是 `card_generator.py` 生成的虚拟
> Visa（不是真实卡）。最初看到的 `SignUpNewMemberMutation` 返回
> `ISSUER_DECLINE / CARD_GENERIC_ERROR` **不是终止状态**，而是 PayPal SignUp
> 链路的预期分支：addCard 失败后 PayPal 服务器自动给 redirect URL 追加
> `addFIContingency=noretry&fallback=1&reason=Q0FSRF9HRU5FUklDX0VSUk9S`
> （base64 = `CARD_GENERIC_ERROR`），把流量导进 `/webapps/hermes` **兜底支付**。
>
> Hermes 里只跑两个 GraphQL：`cardTypes` 查询 + `authorize` mutation
> （`fundingPreference={"balancePreference":"OPT_OUT"}`），后者直接返回
> `returnURL.href = pm-redirects.stripe.com/return/...?status=success`，整条
> $0 trial 至此完成。**OPT_OUT 是 PayPal 用来表达「不走任何资金渠道，纯 $0
> 授权」的关键字段**，所以根本不依赖卡片是否能真实扣款。
>
> 这意味着协议化的真正瓶颈**只剩 hCaptcha passive token**（Stage P3 第 7 步），
> 而且如果能直接构造 hermes 兜底 URL 跳过整个 SignUp 链，captcha 也可能不是必需。

## 上下文衔接

进入 PayPal 之前，Stripe 协议层在 Phase 3 已经做完：

```
Stripe /confirm → setup_intent.next_action.redirect_to_url.url
                  = https://pm-redirects.stripe.com/authorize/acct_X/sa_nonce_Y
                  → 302 → www.paypal.com/agreements/approve?ba_token=BA-XXX
```

PayPal 协议层的入口就是这个 `ba_token`。

## 阶段与端点

### Stage P1 — 落地 + Express Checkout 询价

| #   | Method/Path                                | 作用                                                                                               | Body 关键字段 |
| --- | ------------------------------------------ | -------------------------------------------------------------------------------------------------- | ------------- |
| 1   | `GET  /agreements/approve?ba_token=BA-XXX` | Stripe 跳来的入口，PayPal 设置 session cookies (`x-pp-s` / `nsid` / `tsrce` / `datadome` 等 18 个) | (无)          |

cookies 全部由响应 Set-Cookie 自动建立。后续所有 PayPal 请求都基于这一组 cookies。

### Stage P2 — Pay-With-Card UI 三连

PayPal 落地后的 SPA 自动按用户点击节奏发三次 `/pay`：

| #   | Method/Path                                                                                               | 触发场景                    | 关键 query                               |
| --- | --------------------------------------------------------------------------------------------------------- | --------------------------- | ---------------------------------------- |
| 2   | `POST /pay?token=BA-XXX&paypal_client_cfci=modxo_vaulted_not_recurring-no_interaction`                    | 自动落地探测                | `paypal_client_cfci=...no_interaction`   |
| 3   | `POST /pay?token=BA-XXX&paypal_client_cfci=modxo_vaulted_not_recurring-Pay_With_Card`                     | 用户点 "Pay with Card" 按钮 | `...Pay_With_Card`                       |
| 4   | `POST /pay/?token=BA-XXX&paypal_client_cfci=modxo_vaulted_not_recurring-Continue_To_Payment&ctxId=<UUID>` | 用户点 Continue             | `...Continue_To_Payment&ctxId=<新 UUID>` |

注意：第 4 次 path 多一个尾部 `/`，并附带 `ctxId`（客户端生成的 UUID，每次会话固定）。

### Stage P3 — 风险/Captcha 闸门

这是 PayPal 风控五连：

| #   | Path                                                                                    | 关键参数                                                                                                                                                  | 备注                                                                                                              |
| --- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 5   | `POST /auth/validatecaptcha?paypal_client_cfci=...no_interaction`                       | `_csrf`, `_requestId`, `_hash`, `_sessionID`, `jse`, `hcaptchaToken=NOT_REACHABLE`, `hcaptcha_passive_render_*_time_utc`                                  | **`hcaptchaToken=NOT_REACHABLE` 即可通过**！返回 200 + 7387 字节 HTML（authchallengenodeweb 模板）                |
| 6   | `POST hcaptcha.paypal.com/checksiteconfig?sitekey=bf07db68-5c2e-42e8-8779-ea8384890eea` | (空 body)                                                                                                                                                 | 返回 hsw 任务 JWT                                                                                                 |
| 7   | `POST /auth/verifyhcaptchapassive`                                                      | `_csrf`, `hcaptcha_passive_eval_start_time_utc`, **`hcaptchaToken=P1_<huge_signed_jwt>`**, `publicKey=884d15d9-b649-4bbb-8d1c-2d6f0eed75eb`, `_sessionID` | **真正的 hCaptcha passive 校验**。token 是 hCaptcha 端签名的 JWT (~2200 字符)，需要走 hCaptcha 浏览器/solver 拿到 |
| 8   | `POST /auth/verifygrcenterprise`                                                        | (待解)                                                                                                                                                    | Generic Risk Center 风险评分（之前看到 403 的就是这个）。这次 200 是因为 hCaptcha 通过了                          |
| 9   | `POST hcaptcha.paypal.com/getcaptcha/bf07db68-...`                                      | hCaptcha 端 challenge 启动                                                                                                                                | 同 6 配套                                                                                                         |
| 10  | `POST /auth/validatecaptcha (#2)`                                                       | 同 5 但 ctxId 已建立                                                                                                                                      | 二次校验                                                                                                          |

**关键洞察**：

- `/validatecaptcha` 那条是 PayPal **自家**的端点，接受 `NOT_REACHABLE`
- `/verifyhcaptchapassive` 才是真正提交 hCaptcha 签名 token 的地方
- `_csrf` / `_sessionID` 来自 step 1 落地时的 HTML，需要从首页 HTML 里抓
- `_requestId` / `_hash` 是 PayPal 客户端 JS 算出来的反 CSRF/重放双因子，需要看 JS 代码反推

### Stage P4 — 落到 Guest SignUp 流

风险闸门通过后 PayPal 重定向把你赶进 guest 注册：

| #   | Path                                                                                                           | 关键参数                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 11  | `GET /agreements/approve?modxo_redirect_reason=guest_user&ulOnboardRedirect=true&ba_token=BA-XXX&token=EC-XXX` | **新增 `token=EC-XXX`** — 这是 Express Checkout token，整个 signup 阶段后续都靠它 |
| 12  | `GET /checkoutweb/signup?token=EC-XXX&...&cookieBannerVariant=hidden`                                          | 拿到 SPA 入口 HTML                                                                |

`EC-XXX` 是后续 GraphQL mutation 共享的关键 token。

### Stage P5 — GraphQL 信息查询

入口 SPA 加载后开始拉元数据：

| #   | URL                                      | Body                                                                  | Resp 摘要                                                                                                      |
| --- | ---------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 13  | `POST /graphql?DeferredFeature`          | `{"operationName":"DeferredFeature", ...}`                            | feature flags                                                                                                  |
| 14  | `POST /graphql?GriffinMetadataQuery`     | `{"countryCode":"US","languageCode":"en","shippingCountryCode":"US"}` | 42KB 的地址/电话/币种 metadata。可硬编码或缓存复用                                                             |
| 15  | `POST /graphql?CheckoutSessionDataQuery` | `{"token":"EC-XXX"}`                                                  | 订单详情、cancelUrl 等。`cancelUrl.href` 指向 `pm-redirects.stripe.com/return/.../?status=cancel&token=EC-XXX` |
| 16  | `POST /idapps/graphql`                   | (待补：identity 发现)                                                 | 拿 identity 客户端 token                                                                                       |

### Stage P6 — 双因素手机验证

PayPal 强制要求新用户做手机短信验证：

| #   | URL                                                                 | Body                                                                                                      | Resp                                                                                      |
| --- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 17  | `POST /graphql?InitiateRiskBasedTwoFactorPhoneConfirmationMutation` | `{"locale":{"country":"US","lang":"en"},"phoneCountry":"US","phoneNumber":"6562280644","token":"EC-XXX"}` | `{"authId":"11515595928735444187","challengeId":"7194630413972633186","state":"PENDING"}` |
| 18  | `POST /graphql?ConfirmRiskBasedTwoFactorPhoneConfirmationMutation`  | `{"authId":...,"challengeId":...,"pin":"386729","token":"EC-XXX"}`                                        | `{"state":"CONFIRMED"}`                                                                   |

**实现要点**：

- 用户在前端配置的 SMS provider 在这一步派上用场
- `pin` 字段是 6 位数字短信验证码
- `token` 一定是 `EC-XXX`（不是 `BA-XXX`）

### Stage P7 — 一键注册 + 卡片授权（**会失败但不影响最终结果**）

```
POST /graphql?SignUpNewMemberMutation
```

请求体（JSON，节选）：

```json
{
  "operationName": "SignUpNewMemberMutation",
  "variables": {
    "card": {
      "cardNumber": "4474629798720202",
      "expirationDate": "01/2029",
      "securityCode": "417",
      "type": "VISA"
    },
    "country": "US",
    "email": "calebsullivan64824xof@gmail.com",
    "firstName": "Caleb Sullivan",
    "lastName": "Sullivan",
    "phone": {"countryCode":"1","number":"6562280644","type":"MOBILE"},
    "supportedThreeDsExperiences": ["IFRAME"],
    "token": "EC-4K3778217T470210U",
    "billingAddress": {
      "line1":"6900 Oak Meadow Street","line2":"Apt 368",
      "city":"Yonkers","state":"NY","postalCode":"10701",
      "accountQuality":{"autoCompleteType":"MANUAL","isUserModified":true},
      "country":"US","familyName":"Sullivan","givenName":"Caleb Sullivan"
    },
    "shippingAddress": {"line1":"","city":"","state":"","postalCode":"", ...}
  },
  "query": "mutation SignUpNewMemberMutation(...)"
}
```

**响应（这次 HAR 真实回放，addCard 分支预期失败）**：

实测下虚拟卡触发 `ISSUER_DECLINE` 是必然结果，但 PayPal 不会因此中止 $0 trial；
它会给客户端发一个带 `reason=CARD_GENERIC_ERROR` 的 redirect 让前端去 hermes
兜底（见下面 Stage P8）。

```json
{
  "errors": [
    {
      "message": "ISSUER_DECLINE",
      "checkpoints": ["addCard"],
      "errorData": {
        "0": { "field": "cardNumber", "code": "CARD_GENERIC_ERROR" },
        "accessToken": "S23AAMSlmPIn..."
      },
      "contingency": true,
      "path": ["onboardAccount"],
      "statusCode": 200
    }
  ],
  "data": { "onboardAccount": null }
}
```

**关键洞察（更新）**：

- 整个 PayPal 账号注册 + 卡片授权 + 风控是 **一个** GraphQL mutation
- 看似是「发卡行拒卡」，实际是 PayPal SignUp 链对虚拟卡的预期反应
- $0 trial 的真正完成不依赖这条 mutation 成功，PayPal 内部已经建好了 buyer 账户
  和 BA token，余下的工作交给 Stage P8/P9 的 Hermes 兜底链路完成
- 也就是说 `card_generator.py` 的 Luhn 卡号已经够用，**不需要接真实卡服务**

### Stage P8 — Hermes 兜底重定向（PayPal 服务器驱动）

```
GET /checkoutweb/drop                              # SPA 卸载
GET /webapps/hermes?token=EC-XXX&ba_token=BA-XXX&fromSignupLite=true
                  &addFIContingency=noretry&redirectToHermes=true
                  &fallback=1&reason=Q0FSRF9HRU5FUklDX0VSUk9S
```

- `Q0FSRF9HRU5FUklDX0VSUk9S` = base64 of `CARD_GENERIC_ERROR`
- 这一步是 PayPal 服务器**自动**把客户端从 SignUp SPA 重定向到 hermes 兜底
  支付页面，无需协议层主动构造
- 但**协议层完全可以直接构造这个 URL**，跳过 SignUp + Captcha + 2FA 整段链路；
  cookies 沿用 Stage P1 落地的就行 —— 这是协议化最具捷径价值的发现
- hermes 这一步浏览器实际下载的是 SPA HTML + 一堆 chunk，协议层可以只 GET
  HTML 不下 chunk

### Stage P9 — Hermes GraphQL：`cardTypes` + `authorize` ✨ **真正的支付完成端点**

注意 path 是 `/graphql/`（**带尾斜杠**），与 Stage P5 的 `/graphql` 不同。
body 是 GraphQL **批量数组**（`[{operationName, variables, query}]`）。

#### P9-1: `query cardTypes`

```json
[
  {
    "operationName": "cardTypes",
    "variables": { "billingAgreementId": "EC-XXX", "country": "US" },
    "query": "query cardTypes($billingAgreementId: String!, $country: String!) { billing { cardTypes(billingAgreementId: $billingAgreementId, country: $country) { allowed subTypes __typename } __typename } }"
  }
]
```

响应：

```json
[{"data":{"billing":{"cardTypes":{"allowed":["VISA","DISCOVER","MASTERCARD","AMEX"],"subTypes":[],...}}}}]
```

这一步只是确认允许的卡类型，结果对协议层基本无用，但 PayPal 服务器需要它
来初始化 hermes 上下文，所以**必须发**。

#### P9-2: `mutation authorize` — **这一步直接完成 $0 授权**

```json
[
  {
    "operationName": "authorize",
    "variables": {
      "billingAgreementId": "EC-XXX",
      "fundingPreference": { "balancePreference": "OPT_OUT" },
      "legalAgreements": {}
    },
    "query": "mutation authorize($billingAgreementId: String!, $addressId: String, $fundingPreference: billingFundingPreferenceInput, $legalAgreements: billingLegalAgreementsInput) { billing { authorize(billingAgreementId: $billingAgreementId addressId: $addressId fundingPreference: $fundingPreference legalAgreements: $legalAgreements) { billingAgreementToken paymentAction returnURL { href __typename } buyer { userId __typename } __typename } __typename } }"
  }
]
```

响应（这一条就是支付成功的标志）：

```json
[
  {
    "data": {
      "billing": {
        "authorize": {
          "billingAgreementToken": "BA-XXX",
          "paymentAction": "SALE",
          "returnURL": {
            "href": "https://pm-redirects.stripe.com/return/acct_1HOrSwC6h1nxGoI3/sa_nonce_UZJB.../?status=success&token=EC-XXX"
          },
          "buyer": { "userId": "23DE2U7B4F43L" }
        }
      }
    }
  }
]
```

协议层拿到 `returnURL.href` 后跟随这一次跳转回 Stripe 的 `/return`，再由
Stripe `/poll` (Phase 7) 收尾，整条链路结束。

## 边界与解决思路

### 协议化的真正路线

**首选方案：直接走 Hermes 短路径，跳过 SignUp + Captcha + 2FA**

理由：

1. Stage P3 captcha 是 SignUp SPA 的内部 gate，hermes 兜底页面**不再要求 captcha**
2. Stage P6 SMS 2FA 同理，是 SignUp 流程要求的
3. Stage P8 hermes URL 是 PayPal 服务器编排的，协议层只要复制这组 query 参数
   就能直接跳进 hermes，cookies 沿用 Stage P1 即可
4. Stage P9 的 `cardTypes` + `authorize` 是纯 HTTP，无 captcha

实现路径：

```
Stage P1 (落地 + ba_token)            ← 已实现 (Phase 8)
      ↓ 不发 SignUp 的任何东西，直接构造 hermes URL
Stage P8 (GET /webapps/hermes?...&fallback=1&reason=...)
      ↓
Stage P9-1 (POST /graphql/ cardTypes)
      ↓
Stage P9-2 (POST /graphql/ authorize → returnURL)
      ↓
Stage Stripe-poll                       ← 已实现 (Phase 7)
```

如果 PayPal 拒绝直接 hermes（因为缺 SignUp 建立的 cookies/token），**回退方案**
是老老实实跑完 SignUp + Captcha + 2FA，最后让 PayPal 自己重定向到 hermes。
这条回退路径仍然只需要解决一件事：

**hCaptcha passive token (Stage P3 第 7 步)**

- 真正的 token 来自 hCaptcha 浏览器 SDK，无法纯 HTTP 计算
- 解决方案：
  - (a) 用第三方 hCaptcha solver (2captcha / capsolver) 提交 sitekey + pageurl 拿 token
  - (b) 用一个最小化的 headless 浏览器仅做 hCaptcha 一步，其余仍走协议
  - (c) 复用项目已配置的 `captcha_providers` 体系（i18n 已有 protocol_order/protocol_mode 字段）

**虚拟卡是足够的**：`card_generator.py` 生成的 Luhn 卡号在 SignUp addCard
会触发 `ISSUER_DECLINE`，但这是预期路径，最终通过 hermes `OPT_OUT` 兜底完成。
不需要接 Privacy.com / Capital One Eno 等真实卡服务。

### 可硬编码或单次抓取的常量

- `_csrf`, `_sessionID`, `_requestId`, `_hash`：每次会话独立，从 Stage P1 的 HTML 里抓
- `paypal_client_cfci`：固定字符串模式 `modxo_vaulted_not_recurring-<step>`
- `ctxId`：客户端 UUID，整个会话内复用
- `publicKey=884d15d9-...`：hCaptcha sitekey，长期不变
- `sitekey=bf07db68-...`：hcaptcha.paypal.com 的 sitekey，长期不变
- GriffinMetadata 响应：US/en 的 42KB 元数据可一次抓取打包成静态资源

## 已落地 / 后续 Phase 路线（2026-05-23 修订）

- **Phase 3** ✅ Stripe checkout 协议化（`stripe_http.py` + `proto_stage_stripe_checkout`）
- **Phase 7** ✅ Stripe `/poll` 收尾（`proto_stage_stripe_poll`）
- **Phase 8** ✅ PayPal Stage P1 落地（`paypal_http.py` + `proto_stage_paypal_approve`）
- **Phase 9** 🚧 Hermes 短路径：直接构造 `/webapps/hermes` URL +
  `cardTypes` + `authorize` mutation；这是协议化跑通最有希望的捷径
- **Phase 10** ⏳ 回退路径：完整 SignUp + Captcha + 2FA + addCard，仅在 Phase 9
  失败时启用，依赖 hCaptcha solver 抽象层
- **Phase 11** ✅ 取消 `CHATGPT_PROTOCOL_CHECKOUT_LIVE` 闸门：前端 Checkout 模式
  选「协议模式」即生效，`complete_paypal_checkout_protocol` 不再读环境变量
