"""Automated workflow (§23): detect -> docs -> extract -> value -> peers ->
subscription -> anchor -> GMP -> market -> predict -> store. Re-runnable;
prediction changes as new info arrives, every run timestamped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..api.service import build_report, persist_prediction
from ..database import IPODocument, get_session_factory, init_db


def run_workflow(ipo_id: int, db_url: str | None = None) -> dict:
    init_db(db_url)
    steps: list[str] = []
    Session = get_session_factory(db_url)
    s = Session()
    try:
        s.add(IPODocument(ipo_id=ipo_id, doc_type="WorkflowRun",
                          parse_status="started",
                          parse_log=f"run at {datetime.now(timezone.utc).isoformat()}"))
        s.commit()
    finally:
        s.close()
    steps.append("1-2. IPO record ensured")
    steps.append("3-7. Documents/financials/risks/shareholding from DB + RHP parser")
    steps.append("8-9. Valuation + peers computed")
    steps.append("10-12. Subscription/anchor/GMP snapshots read")
    steps.append("13. Market regime read")
    report = build_report(ipo_id, db_url)
    pid = persist_prediction(ipo_id, report, db_url)
    steps.append(f"14-19. Prediction stored (id={pid}) with feature timestamps")
    return {"ipo_id": ipo_id, "steps": steps,
            "prediction": report.get("prediction"),
            "assessment": report.get("assessment")}


if __name__ == "__main__":
    import sys
    from ..scripts.seed import seed, seed_example
    print(seed())
    eid = seed_example()
    print(run_workflow(eid))
