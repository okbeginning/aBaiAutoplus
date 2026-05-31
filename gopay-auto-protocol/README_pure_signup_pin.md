# GoPay Android 2.10.0 纯协议注册/登录/设置 PIN

最终入口只需要传 PIN；脚本会自动买 Indonesia SMSCloud 号码、轮询 OTP、注册、刷新登录态、触发 PIN 二次 OTP 并设置 PIN：

```bash
python3 android_gopay_2.10.0/protocol/pure_pin_only.py --pin 736294
```

默认行为：

- SMSCloud：`service=ni`、`country=6`、优先 `2.25` 价格桶，不足时自动尝试可用库存价。
- X-E1：默认 `enhanced` 纯 Python signer，不需要 adb / Frida / App。
- 设备：每次自动生成 fresh `X-UniqueId`、`D1`、`X-M1`、`X-Session-ID`。
- 重试：遇到回收号、OTP timeout、CVS/device 429 会换号/换设备继续。
- 状态文件：写到 `android_gopay_2.10.0/protocol/runs/*.json`。

## 已验证成功证据

```text
android_gopay_2.10.0/protocol/runs/pure_pin_only_attempt1_20260530_054154.json
phone: +6283841524899
customer_id: 900714930
PIN: 736294
```

成功时序：

```text
login_methods                         401 user:not_found
cvs_methods                           200
cvs_initiate                          200
cvs_verify                            200
customer_signup_1_auth_id_...         201
refresh_after_signup_token            201
pin_allowed                           200
pin_cvs_methods                       200
pin_cvs_initiate                      200
pin_cvs_verify                        200
pin_setup_token_after_otp             200
profile_after_pin_setup               200/记录态（若返回 is_pin_setup=false 则失败）
```

## 关键协议点

- Signup Basic：`base64("bb648413-b637-443a-8ebf-176cf9b5dc32")`。
- Signup `client_name`：wire body 使用 JSON unicode escape：`gopay\u003aconsumer\u003aapp`，后端解码为 `gopay:consumer:app`，同时避开 Tencent WAF。
- Signup send path：`/v7//customers/signup`；X-E1 sign path：`/v7/customers/signup`。
- Signup 直返 RS256 access token 会被 customer API 判 `Session is revoked`；必须马上用 `refresh_token` 调 `/goto-auth/token grant_type=refresh_token` 换正常 goto-auth session。
- PIN 设置使用 `flow=goto_pin_wa_sms` 的二次 CVS OTP，最终调用 `customer.gopayapi.com/api/v2/users/pins/setup/tokens`。

## 常用调试命令

只生成首包，不买号：

```bash
python3 android_gopay_2.10.0/protocol/pure_pin_only.py --pin 736294 --dry-run --quiet
```

静态编译检查：

```bash
python3 -m py_compile \
  android_gopay_2.10.0/protocol/gopay_protocol.py \
  android_gopay_2.10.0/protocol/full_pure_signup_pin.py \
  android_gopay_2.10.0/protocol/pure_pin_only.py \
  android_gopay_2.10.0/protocol/smscloud_client.py
```

底层完整 runner：

```bash
python3 android_gopay_2.10.0/protocol/full_pure_signup_pin.py --help
```
