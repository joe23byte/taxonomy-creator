import io
import json

import pandas as pd
import pytest

from app import importers


def test_json_canonical_and_missing_metadata():
    data = [{"conversation_id": "A1", "turns": [{"speaker": "Customer", "text": "My bill is wrong"},
                                                 {"speaker": "rep", "text": "Let me check"}]},
            {"turns": [{"speaker": "customer", "text": "Hello"}]},
            {"conversation_id": "EMPTY", "turns": []}]
    res = importers.parse_upload([("x.json", json.dumps(data).encode())])
    assert len(res.records) == 2
    assert res.records[0]["turns"][1]["speaker"] == "agent"
    assert res.records[1]["conversation_id"].startswith("IMPORT-")
    assert any(i["level"] == "error" for i in res.issues)
    assert any("metadata" in i["message"] for i in res.issues)


def test_csv_wide_with_transcript_column():
    csv = ("conversation_id,channel,transcript\n"
           "C1,WhatsApp,\"Customer: I topped up but no credit\nAgent: Checking\"\n")
    res = importers.parse_upload([("x.csv", csv.encode())])
    assert res.format == "csv"
    assert res.records[0]["channel"] == "whatsapp"
    assert [t["speaker"] for t in res.records[0]["turns"]] == ["customer", "agent"]


def test_csv_turn_level_with_custom_mapping():
    csv = "conv,who,utt,medium\nX,client,Slow internet,chat\nX,advisor,Sorry,chat\nY,client,Lost SIM,chat\n"
    res = importers.parse_upload([("x.csv", csv.encode())])
    assert res.needs_mapping  # columns cannot be guessed
    res = importers.parse_upload([("x.csv", csv.encode())],
                                 mapping={"conversation_id": "conv", "speaker": "who", "text": "utt", "channel": "medium"})
    assert len(res.records) == 2
    assert res.records[0]["turns"][1] == {"speaker": "agent", "text": "Sorry"}


def test_excel_import():
    df = pd.DataFrame([{"conversation_id": "E1", "segment": "Prepaid", "transcript": "Customer: Hi\nAgent: Hello"}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    res = importers.parse_upload([("x.xlsx", buf.getvalue())])
    assert res.records[0]["segment"] == "prepaid"


def test_txt_one_file_per_interaction_and_separator():
    res = importers.parse_upload([("call one.txt", b"Customer: hi\nAgent: hello"), ("b.txt", b"Unlabelled text only")])
    assert [r["conversation_id"] for r in res.records] == ["call-one", "b"]
    assert res.records[1]["turns"] == [{"speaker": "customer", "text": "Unlabelled text only"}]
    res = importers.parse_upload([("multi.txt", b"Customer: a\n---\nCustomer: b")], txt_separator="---")
    assert len(res.records) == 2


def test_invalid_json_message_has_no_content():
    with pytest.raises(importers.ImportErrorSafe) as e:
        importers.parse_upload([("x.json", b'{"secret transcript": ')])
    assert "secret" not in str(e.value)


def test_commit_skips_existing(conn):
    res = importers.parse_upload([("x.json", json.dumps([{"conversation_id": "A", "turns": ["Customer: hi"]}]).encode())])
    assert importers.commit(conn, "a", "json", res.records)["imported"] == 1
    out = importers.commit(conn, "a", "json", res.records)
    assert out == {"import_id": out["import_id"], "imported": 0, "skipped_existing": 1}
