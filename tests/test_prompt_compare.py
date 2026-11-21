"""The counting rule of scripts/prompt_compare.py."""
import prompt_compare


def row(version, kind, status=200, abstained=False):
    return {"id": "q", "version": version, "type": kind, "status": status, "abstained": abstained}


def test_failed_call_stays_in_the_denominator_and_is_not_an_abstention():
    rows = [row("v1", "unanswerable", abstained=True), row("v1", "unanswerable", status=502, abstained=None),
            row("v1", "factoid"), row("v1", "list", abstained=True), row("v2", "unanswerable")]
    s = prompt_compare.summarize(rows, ["v1", "v2"])
    assert s["v1"] == {"unanswerable": 2, "abstained_unanswerable": 1, "answerable": 2, "abstained_answerable": 1,
                       "failed": 1}
    assert s["v2"]["unanswerable"] == 1 and s["v2"]["abstained_unanswerable"] == 0 and s["v2"]["failed"] == 0
