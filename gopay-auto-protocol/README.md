# GoPay 纯协议注册 / 登录 / 设置 PIN 使用教程

#  本脚本为了尽快分享开源，只做了gopay纯协议注册，只对接了一个接码平台，目前还有很多完善的地方，执行单线程单号跑，还是得靠各位佬进行开发研究！

## TG 交流群 / 赞赏

有问题可以进 TG 交流群一起交流：`@JNMHUB`

L 站：<https://linux.do/u/lijinmu>

<img src="./tg.png" alt="TG交流群 @JNMHUB" width="320" />

如果这个项目对你有帮助，也欢迎随缘赞赏支持：

<img src="./赞赏.png" alt="赞赏码" width="320" />

## 配置好接码KEY 之后，这样执行就行了

```bash
python3 android_gopay_2.10.0/protocol/pure_pin_only.py --pin 736294
```


这个目录是一个纯 Python 协议脚本包，主要入口是 `pure_pin_only.py`。脚本会自动：

1. 从 SMSCloud 接码平台购买印度尼西亚号码；
2. 轮询短信 OTP；
3. 完成注册 / 登录；
4. 刷新登录态；
5. 发起设置 PIN 的二次 OTP；
6. 提交并设置新的 PIN；
7. 将运行状态保存为 JSON。

## 文件说明

- `pure_pin_only.py`：推荐入口，只需要传入要设置的 PIN。
- `full_pure_signup_pin.py`：完整底层 runner，支持手动号码、复用订单、调试签名等高级参数。
- `smscloud_client.py`：SMSCloud 接码平台 API 封装。
- `gopay_protocol.py`：GoPay 协议、签名、设备指纹和请求封装。
- `README_pure_signup_pin.md`：旧版说明和历史验证记录。

## 环境准备

需要 Python 3.10+，并安装依赖：

```bash
pip install requests cryptography
```

在 Windows PowerShell 中进入项目目录：

```powershell
cd C:\Users\jnmgp\Desktop\pure_pin_only_bundle_20260530_065956
```

## 接码平台 KEY 在哪里设置

接码平台https://smscloud.sbs/sms接码平台使用的是 SMSCloud，KEY 参数名是 `sms_key`，读取优先级如下：

1. 命令行参数 `--sms-key`，优先级最高；
2. 环境变量 `SMSCLOUD_KEY`；
3. 代码里的默认值 `KEY_DEFAULT`。

对应代码位置：

- `pure_pin_only.py`

```python
ap.add_argument("--sms-key", default=os.getenv("SMSCLOUD_KEY", KEY_DEFAULT))
```

- `full_pure_signup_pin.py`

```python
KEY_DEFAULT = "..."
ap.add_argument("--sms-key", default=os.getenv("SMSCLOUD_KEY", KEY_DEFAULT))
```

推荐使用环境变量，不要直接把自己的 KEY 写死到代码里：

```powershell
$env:SMSCLOUD_KEY="你的_SMSCloud_API_KEY"
python .\pure_pin_only.py --pin 736294 --skip-waf-preflight
```

也可以临时通过命令行传入：

```powershell
python .\pure_pin_only.py --pin 736294 --sms-key "你的_SMSCloud_API_KEY" --skip-waf-preflight
```

## 快速使用

推荐命令：

```powershell
$env:SMSCLOUD_KEY="你的_SMSCloud_API_KEY"
python .\pure_pin_only.py --pin 736294 --skip-waf-preflight
```

参数说明：

- `--pin 736294`：要设置的新 PIN，必填。
- `--sms-key`：SMSCloud 接码平台 KEY；也可以用环境变量 `SMSCLOUD_KEY`。
- `--attempts 8`：失败、超时、号码被占用时最多换号重试次数，默认 8。
- `--otp-timeout 240`：每个号码等待 OTP 的秒数，默认 240。
- `--quiet`：减少 HTTP 调试输出。
- `--dry-run`：只构造首包，不买号、不完整执行。
- `--skip-waf-preflight`：跳过预探测。当前精简包里没有 `probe_initiate_waf.py`，所以建议加上这个参数。

## 输出与日志

运行后会在日志中看到 SMSCloud 余额、订单、手机号、OTP 和最终状态文件路径。

新增手机号日志格式如下：

```text
[phone] acquired input=628xxxxxxxxxx normalized=+628xxxxxxxxxx
```

状态 JSON 默认写入：

```text
.\runs\pure_pin_only_attempt*.json        # 使用 pure_pin_only.py 且未指定 --out 时
android_gopay_2.10.0/protocol/runs/*.json # 直接使用 full_pure_signup_pin.py 且未指定 --out 时
```

如果想指定输出文件：

```powershell
python .\pure_pin_only.py --pin 736294 --skip-waf-preflight --out .\runs\latest.json
```

## 手动号码 / 复用订单

如果已经在接码平台买好了号码，可以使用底层 runner：

```powershell
python .\full_pure_signup_pin.py `
  --phone 628xxxxxxxxxx `
  --sms-order-id 订单ID `
  --sms-key "你的_SMSCloud_API_KEY" `
  --pin 736294 `
  --finish-sms-order
```

如果不使用接码平台，手动传 OTP：

```powershell
python .\full_pure_signup_pin.py `
  --phone 628xxxxxxxxxx `
  --otp 123456 `
  --pin-otp 654321 `
  --pin 736294
```

## 常用检查

编译检查：

```powershell
python -m py_compile .\gopay_protocol.py .\full_pure_signup_pin.py .\pure_pin_only.py .\smscloud_client.py
```

查看完整参数：

```powershell
python .\pure_pin_only.py --help
python .\full_pure_signup_pin.py --help
```

## 注意事项

- `--pin` 是必填参数，入口脚本不会使用默认 PIN。
- 推荐把 `SMSCLOUD_KEY` 设置为环境变量，避免误提交真实 KEY。
- 运行状态文件里会记录参数、手机号、订单和 OTP 等调试信息，请妥善保存。
- 如果遇到 OTP 超时、号码已注册、服务端 429，`pure_pin_only.py` 会按 `--attempts` 自动换号重试。
