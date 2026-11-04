import json
import os
import urllib.request
import urllib.error

from careinsight.tools import get_screening_rate
from careinsight.age_tool import get_screening_by_age


def call_model(messages, tools=None):
    payload = {
        "model": os.environ["DEEPSEEK_MODEL"],
        "messages": messages,
        "thinking": {"type": "disabled"},
        "max_tokens": 800,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        os.environ["DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"].strip(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)

    print("Tokens used in this model call:", result.get("usage", {}).get("total_tokens"))
    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型输出被截断，暂停处理。")
    return choice["message"]


def main():
    tools = [{
        "type": "function",
        "function": {
            "name": "get_screening_rate",
            "description": (
                "Calculate adult depression screening record coverage "
                "from local Synthea data. Only validated year 2020 is supported."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "enum": [2020]}
                },
                "required": ["year"],
                "additionalProperties": False,
            },
        },
    }]

    import copy
    age_schema = copy.deepcopy(tools[0])
    age_schema["function"]["name"] = "get_screening_by_age"
    age_schema["function"]["description"] = (
        "Compare screening record coverage across age groups "
        "18–39, 40–64, and 65+ in 2020. "
        "Use for age comparisons and finding the lowest age group."
    )
    tools.append(age_schema)

    question = input("Enter your analysis question: ").strip()
    if not question:
        print("问题为空，请重新运行并输入问题。")
        return
    messages = [
        {
            "role": "system",
            "content": (
                "Always write the final report in English. Display coverage percentages to two decimal places. 你是 CareInsight 分析助手。涉及数据的问题必须调用工具，"
                "不得猜测数字。当前支持 2020 年总体覆盖率和年龄分组比较。总体问题调用 get_screening_rate，年龄组问题调用 get_screening_by_age。一次只调用最相关的一个工具。分组回答应列出各组人数和覆盖率，不得编造差异原因或声称统计显著。"
                "回答应包含年份、分子、分母、百分比及合成数据局限。"
                "未记录筛查不等于没有实施筛查。"
                "不得推测实际覆盖率高于或低于记录覆盖率。"
                "根据工具的 denominator_definition 解释分母，"
                "并明确缺失死亡日期按无死亡记录处理。"
                "coverage 是 0–1 比例，展示时转换为百分比。"
                "工具结果中的 definition_file 只是路径，不表示你已读取文件。"
            ),
        },
        {"role": "user", "content": question},
    ]

    # 第一版的保守范围检查：不允许替换用户指定的年份。
    import re
    mentioned_years = set(
        re.findall(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])", question)
    )
    unsupported_years = mentioned_years - {"2020"}

    if unsupported_years:
        print(
            "分析未执行：问题涉及尚未支持的年份："
            + "、".join(sorted(unsupported_years))
        )
        print("目前仅支持 2020 年，不会使用其他年份的数据代替。")
        return

    print("User question:", question)
    reply = call_model(messages, tools)
    calls = reply.get("tool_calls") or []

    if not calls:
        print("本次未执行分析工具。当前支持 2020 年总体覆盖率和年龄分组比较。")
        return
    if len(calls) != 1:
        raise RuntimeError("本次请求了多个工具调用，超出当前演示范围。")

    tool_call = calls[0]
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])

    # 只允许一个明确授权的工具及其参数，不能执行模型生成的任意代码。
    allowed_tools = {
        "get_screening_rate": get_screening_rate,
        "get_screening_by_age": get_screening_by_age,
    }
    if name not in allowed_tools:
        raise RuntimeError("模型请求了不支持的工具。")
    if not isinstance(args, dict) or set(args) != {"year"}:
        raise RuntimeError("工具参数格式不正确。")

    print("\nSelected tool:", name)
    print("Tool arguments:", args)

    result = allowed_tools[name](**args)
    print("Local tool result:", json.dumps(result, ensure_ascii=False))

    messages.append(reply)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    })

    # 第二次只让模型解释已经执行得到的结果。
    answer = call_model(messages)
    content = answer.get("content")
    if not content:
        raise RuntimeError("模型没有返回报告正文。")
    print("\n=== AI Analysis Report (Review Required) ===")
    print(content)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print("API 请求失败，HTTP 状态码：", error.code)
    except urllib.error.URLError:
        print("网络连接失败。")
    except TimeoutError:
        print("请求超时。")
    except (ValueError, RuntimeError) as error:
        print("分析暂停：", error)
