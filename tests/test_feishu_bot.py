from __future__ import annotations

import json

from feishu_bot.core import extract_text, normalize_text, parse_event_payload


def test_normalize_text_removes_mention_tokens() -> None:
    assert normalize_text("@_user_1  你好  \n  世界") == "你好\n世界"


def test_extract_text_supports_post_messages() -> None:
    payload = {
        "zh_cn": {
            "title": "日报",
            "content": [
                [{"tag": "text", "text": "第一行"}],
                [{"tag": "text", "text": "第二行"}],
            ],
        }
    }
    assert extract_text("post", json.dumps(payload, ensure_ascii=False)) == "日报\n第一行\n第二行"


def test_parse_event_payload_collects_mentions() -> None:
    payload = {
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": "ou_sender",
                }
            },
            "message": {
                "message_id": "om_123",
                "chat_id": "oc_456",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "@_user_1 帮我总结一下"}, ensure_ascii=False),
                "mentions": [
                    {
                        "id": {
                            "open_id": "ou_bot",
                        }
                    }
                ],
            },
        }
    }

    message = parse_event_payload(payload)
    assert message.message_id == "om_123"
    assert message.chat_id == "oc_456"
    assert message.text == "帮我总结一下"
    assert message.mentioned_open_ids == ("ou_bot",)
    assert message.sender_open_id == "ou_sender"

