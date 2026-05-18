from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from db.models import (
    ChannelSend,
    HitlReview,
    RescueAnalysis,
    RescueDraft,
    RescuePost,
    create_tables,
    get_session,
)

st.set_page_config(page_title="Food Rescue HITL", page_icon="🌿", layout="wide")
create_tables()

REJECT_REASONS = [
    "Wrong content",
    "Off-topic",
    "Low quality",
    "Safety concern",
    "Other",
]

VALID_ACTIONS = {"approved", "edited", "rejected", "flagged"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_pending() -> list[dict]:
    with get_session() as db:
        drafts = (
            db.query(RescueDraft)
            .filter(RescueDraft.hitl_status == "pending")
            .order_by(RescueDraft.created_at.asc())
            .limit(50)
            .all()
        )
        result = []
        for d in drafts:
            analysis = db.query(RescueAnalysis).filter_by(id=d.analysis_id).first()
            post = db.query(RescuePost).filter_by(id=analysis.post_id).first() if analysis else None
            result.append({
                "draft_id": d.id,
                "platform": d.platform,
                "content": d.content,
                "confidence": d.confidence,
                "created_at": d.created_at,
                "raw_text": post.raw_text if post else "",
                "urgency_hint": post.urgency_hint if post else "unknown",
                "ingredients": json.loads(analysis.ingredients or "[]") if analysis else [],
            })
        return result


def load_stats() -> dict:
    with get_session() as db:
        pending = db.query(RescueDraft).filter_by(hitl_status="pending").count()
        approved_today = (
            db.query(HitlReview)
            .filter(HitlReview.action == "approved")
            .count()
        )
        reviews = db.query(HitlReview).all()
        return {
            "pending": pending,
            "approved_today": approved_today,
            "total_reviews": len(reviews),
        }


def apply_action(draft_id: str, action: str, editor_note: str, final_content: str) -> None:
    with get_session() as db:
        draft = db.query(RescueDraft).filter_by(id=draft_id).first()
        if not draft:
            return

        review = HitlReview(
            draft_id=draft_id,
            action=action,
            editor_note=editor_note or None,
            final_content=final_content if action == "edited" else None,
        )
        db.add(review)

        new_status = action if action in {"rejected", "flagged"} else "approved"
        draft.hitl_status = new_status

        if action in {"approved", "edited"}:
            send = ChannelSend(
                draft_id=draft_id,
                platform=draft.platform,
                status="sent",
            )
            db.add(send)

        db.commit()


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("🌿 Food Rescue — HITL Dashboard")

stats = load_stats()
col1, col2, col3 = st.columns(3)
col1.metric("Bekleyen", stats["pending"])
col2.metric("Onaylanan (toplam)", stats["approved_today"])
col3.metric("Toplam İnceleme", stats["total_reviews"])

st.divider()

tab_pending, tab_history = st.tabs(["📋 Bekleyen Taslaklar", "📜 Geçmiş"])

with tab_pending:
    pending = load_pending()
    if not pending:
        st.info("Bekleyen taslak yok. 🎉")
    else:
        for item in pending:
            with st.expander(
                f"[{item['urgency_hint'].upper()}] {item['platform']} — "
                f"{item['created_at'].strftime('%H:%M') if item['created_at'] else '?'}  "
                f"(conf: {item['confidence']:.2f})" if item["confidence"] else "",
                expanded=True,
            ):
                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown("**Orijinal Mesaj**")
                    st.text_area("", value=item["raw_text"], height=120, key=f"orig_{item['draft_id']}", disabled=True)
                    if item["ingredients"]:
                        names = [i.get("name", "") for i in item["ingredients"]]
                        st.caption(f"Malzemeler: {', '.join(names)}")

                with col_right:
                    st.markdown("**Agent Taslak Yanıt**")
                    draft_content = st.text_area(
                        "",
                        value=item["content"],
                        height=200,
                        key=f"content_{item['draft_id']}",
                    )

                c1, c2, c3, c4 = st.columns(4)

                if c1.button("✅ Onayla", key=f"approve_{item['draft_id']}"):
                    apply_action(item["draft_id"], "approved", "", item["content"])
                    st.success("Onaylandı!")
                    st.rerun()

                if c2.button("✏️ Düzenle + Onayla", key=f"edit_{item['draft_id']}"):
                    apply_action(item["draft_id"], "edited", "Edited by moderator", draft_content)
                    st.success("Düzenlendi ve onaylandı!")
                    st.rerun()

                reject_reason = st.selectbox(
                    "Reddet nedeni",
                    REJECT_REASONS,
                    key=f"reason_{item['draft_id']}",
                )
                if c3.button("❌ Reddet", key=f"reject_{item['draft_id']}"):
                    apply_action(item["draft_id"], "rejected", reject_reason, "")
                    st.warning("Reddedildi.")
                    st.rerun()

                if c4.button("🏷️ Eğitim Verisi", key=f"flag_{item['draft_id']}"):
                    apply_action(item["draft_id"], "flagged", "Flagged for training", "")
                    st.info("Eğitim verisi olarak işaretlendi.")
                    st.rerun()

with tab_history:
    with get_session() as db:
        reviews = (
            db.query(HitlReview)
            .order_by(HitlReview.reviewed_at.desc())
            .limit(100)
            .all()
        )
        if not reviews:
            st.info("Henüz inceleme yapılmamış.")
        else:
            for r in reviews:
                st.write(
                    f"**{r.action.upper()}** — {r.reviewed_at.strftime('%Y-%m-%d %H:%M')} "
                    f"| Draft: `{r.draft_id[:8]}...`"
                )
                if r.editor_note:
                    st.caption(r.editor_note)
