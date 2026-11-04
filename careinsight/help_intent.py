import re


def normalize(text):
    """Normalize common punctuation and spacing."""
    text = str(text).lower().strip()
    text = re.sub(r"[?!？！，。.,]", "", text)
    return re.sub(r"\s+", " ", text)


def is_product_help(text):
    """Recognize common requests about the product itself."""
    text = normalize(text)

    exact_questions = {
        "what it is",
        "what is it",
        "what is this",
        "what is careinsight",
        "what can you do",
        "what can this ai do",
        "what can i ask",
        "how do i use this",
        "how does this tool work",
        "what does this app do",
        "help",
        "这ai能干啥",
        "这个ai能干什么",
        "你能做什么",
        "你能干什么",
        "有什么功能",
        "怎么用",
        "这个怎么用",
    }

    help_phrases = (
        "how this tool works",
        "how this app works",
        "what this tool can do",
        "what this app can do",
    )

    return (
        text in exact_questions
        or any(phrase in text for phrase in help_phrases)
    )


def wants_product_help(state):
    """Use the latest clarification when one exists."""
    history = state.get("clarification_history") or []

    if history:
        latest_answer = history[-1].get("answer", "")
        return is_product_help(latest_answer)

    return is_product_help(state.get("question", ""))
