import json
import os
import urllib.request
import urllib.error

payload = {
    "model": os.environ["DEEPSEEK_MODEL"],
    "messages": [
        {"role": "user", "content": "Reply with exactly: Connection OK"}
    ],
    "max_tokens": 128,
    "stream": False,
}

request = urllib.request.Request(
    os.environ["DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"].strip(),
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)

    message = result["choices"][0]["message"]
    print("API 请求成功")
    print("模型回复：", message.get("content") or "（正文为空）")
    print("结束原因：", result["choices"][0].get("finish_reason"))
    print("Token 用量：", result.get("usage", {}))

except urllib.error.HTTPError as error:
    print("API 请求失败，HTTP 状态码：", error.code)
    import re
    detail = error.read(8192).decode("utf-8", errors="replace")
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        detail = detail.replace(key, "[密钥已隐藏]")
    detail = re.sub(r"sk-[A-Za-z0-9_-]+", "[密钥已隐藏]", detail)
    print("错误详情：", detail[:2000])

except urllib.error.URLError:
    print("连接失败：请检查网络或接口地址。")
except TimeoutError:
    print("请求超时：暂时不要重复运行，把提示告诉我。")
