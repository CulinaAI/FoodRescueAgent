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

_REDDIT_CREDS_AVAILABLE = all([
    os.getenv("REDDIT_CLIENT_ID"),
    os.getenv("REDDIT_CLIENT_SECRET"),
    os.getenv("REDDIT_USERNAME"),
    os.getenv("REDDIT_PASSWORD"),
])

# Safety gate: auto-posting to Reddit is OFF by default. When disabled, an approved
# reply is logged + shown for the moderator to copy manually — no comment is created.
# This protects the bot account from subreddit-rule / anti-spam bans (esp. pre-launch).
_REDDIT_POST_ENABLED = os.getenv("REDDIT_POST_ENABLED", "false").lower() == "true"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_reddit():
    import praw
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        username=os.getenv("REDDIT_USERNAME", ""),
        password=os.getenv("REDDIT_PASSWORD", ""),
        user_agent=os.getenv("REDDIT_USER_AGENT", "CulinaAI FoodRescueBot/1.0"),
    )


def post_reddit_reply(reddit_post_id: str, content: str) -> str | None:
    """Posts a comment on the Reddit submission. Returns comment ID or None on failure."""
    try:
        reddit = _get_reddit()
        submission = reddit.submission(id=reddit_post_id)
        comment = submission.reply(content)
        return comment.id
    except Exception as exc:
        st.error(f"Reddit'e yorum gönderilemedi: {exc}")
        return None


def load_pending(platform_filter: str = "all") -> list[dict]:
    with get_session() as db:
        query = db.query(RescueDraft).filter(RescueDraft.hitl_status == "pending")
        if platform_filter != "all":
            query = query.filter(RescueDraft.platform == platform_filter)
        drafts = query.order_by(RescueDraft.created_at.asc()).limit(50).all()

        result = []
        for d in drafts:
            analysis = db.query(RescueAnalysis).filter_by(id=d.analysis_id).first()
            post = db.query(RescuePost).filter_by(id=analysis.post_id).first() if analysis else None
            result.append({
                "draft_id": d.id,
                "platform": d.platform,
                "content": d.content,
                "confidence": d.confidence or 0.0,
                "created_at": d.created_at,
                "raw_text": post.raw_text if post else "",
                "urgency_hint": post.urgency_hint if post else "unknown",
                "ingredients": json.loads(analysis.ingredients or "[]") if analysis else [],
                "subreddit": post.subreddit if post else None,
                "post_title": post.post_title if post else None,
                "post_url": post.post_url if post else None,
                "source_id": post.source_id if post else None,
            })
        return result


def load_stats() -> dict:
    with get_session() as db:
        pending = db.query(RescueDraft).filter_by(hitl_status="pending").count()
        approved = db.query(HitlReview).filter(HitlReview.action == "approved").count()
        reviews = db.query(HitlReview).count()
        reddit_count = db.query(RescueDraft).filter_by(platform="reddit").count()
        return {
            "pending": pending,
            "approved": approved,
            "total_reviews": reviews,
            "reddit_count": reddit_count,
        }


def apply_action(
    draft_id: str,
    action: str,
    editor_note: str,
    final_content: str,
    source_id: str | None = None,
    platform: str = "generic",
) -> str | None:
    """Applies HITL action. For Reddit approve/edit, posts comment and returns comment ID."""
    comment_id: str | None = None

    if action in {"approved", "edited"} and platform == "reddit" and source_id:
        if _REDDIT_POST_ENABLED and _REDDIT_CREDS_AVAILABLE:
            comment_id = post_reddit_reply(source_id, final_content)
        # Dry-run (default) or no creds: mark approved, moderator copies the reply manually

    with get_session() as db:
        draft = db.query(RescueDraft).filter_by(id=draft_id).first()
        if not draft:
            return None

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
                external_id=comment_id,
                status="sent" if comment_id else "pending_manual",
            )
            db.add(send)

        db.commit()

    return comment_id


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("🌿 Food Rescue — HITL Dashboard")

stats = load_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Bekleyen", stats["pending"])
c2.metric("Onaylanan", stats["approved"])
c3.metric("Toplam İnceleme", stats["total_reviews"])
c4.metric("Reddit Post", stats["reddit_count"])

if not _REDDIT_CREDS_AVAILABLE:
    st.warning(
        "Reddit kimlik bilgileri eksik (REDDIT_CLIENT_ID / SECRET / USERNAME / PASSWORD). "
        "Onaylanan Reddit yanıtları panoya kopyalanacak — otomatik yorum gönderilmeyecek."
    )

st.divider()

tab_pending, tab_history = st.tabs(["📋 Bekleyen Taslaklar", "📜 Geçmiş"])

with tab_pending:
    platform_filter = st.radio(
        "Platform",
        ["all", "reddit", "telegram", "manual"],
        horizontal=True,
        format_func=lambda x: {"all": "🌐 Tümü", "reddit": "🤖 Reddit", "telegram": "📱 Telegram", "manual": "✍️ Manuel"}[x],
    )

    pending = load_pending(platform_filter)

    if not pending:
        st.info("Bekleyen taslak yok. 🎉")
    else:
        for item in pending:
            is_reddit = item["platform"] == "reddit"
            platform_badge = "🤖 Reddit" if is_reddit else "📱 Telegram" if item["platform"] == "telegram" else "✍️ Manuel"
            urgency_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item["urgency_hint"], "⚪")
            conf = item["confidence"]

            expander_label = (
                f"{urgency_color} [{item['urgency_hint'].upper()}] "
                f"{platform_badge}"
                + (f" · r/{item['subreddit']}" if item.get("subreddit") else "")
                + f" · conf: {conf:.2f}"
                + (f" · {item['created_at'].strftime('%H:%M')}" if item.get("created_at") else "")
            )

            with st.expander(expander_label, expanded=True):
                # Reddit context header
                if is_reddit and item.get("post_title"):
                    st.markdown(
                        f"**r/{item['subreddit']}** — "
                        + (f"[{item['post_title']}]({item['post_url']})" if item.get("post_url") else item["post_title"])
                    )

                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown("**Orijinal Mesaj**")
                    st.text_area(
                        "",
                        value=item["raw_text"],
                        height=120,
                        key=f"orig_{item['draft_id']}",
                        disabled=True,
                    )
                    if item["ingredients"]:
                        names = [i.get("name", "") for i in item["ingredients"]]
                        st.caption(f"Malzemeler: {', '.join(names)}")

                    if is_reddit and item.get("post_url"):
                        st.link_button("🔗 Reddit'te Aç", item["post_url"])

                with col_right:
                    st.markdown("**Agent Taslak Yanıt**")
                    draft_content = st.text_area(
                        "",
                        value=item["content"],
                        height=200,
                        key=f"content_{item['draft_id']}",
                    )

                btn1, btn2, btn3, btn4 = st.columns(4)

                approve_label = "✅ Onayla" + (" + Reddit Yorum" if is_reddit and _REDDIT_CREDS_AVAILABLE else "")
                if btn1.button(approve_label, key=f"approve_{item['draft_id']}"):
                    comment_id = apply_action(
                        item["draft_id"], "approved", "",
                        item["content"],
                        source_id=item.get("source_id"),
                        platform=item["platform"],
                    )
                    if is_reddit and comment_id:
                        st.success(f"Onaylandı ve Reddit'e gönderildi. Yorum ID: `{comment_id}`")
                    elif is_reddit:
                        st.info("Onaylandı (auto-post kapalı/dry-run) — yanıtı manuel yapıştırın:")
                        st.code(item["content"])
                    else:
                        st.success("Onaylandı!")
                    st.rerun()

                edit_label = "✏️ Düzenle + Onayla" + (" + Reddit" if is_reddit and _REDDIT_POST_ENABLED and _REDDIT_CREDS_AVAILABLE else "")
                if btn2.button(edit_label, key=f"edit_{item['draft_id']}"):
                    comment_id = apply_action(
                        item["draft_id"], "edited", "Edited by moderator",
                        draft_content,
                        source_id=item.get("source_id"),
                        platform=item["platform"],
                    )
                    if is_reddit and comment_id:
                        st.success(f"Düzenlendi ve Reddit'e gönderildi. Yorum ID: `{comment_id}`")
                    elif is_reddit:
                        st.info("Düzenlendi (auto-post kapalı/dry-run) — yanıtı manuel yapıştırın:")
                        st.code(draft_content)
                    else:
                        st.success("Düzenlendi ve onaylandı!")
                    st.rerun()

                reject_reason = st.selectbox(
                    "Reddet nedeni",
                    REJECT_REASONS,
                    key=f"reason_{item['draft_id']}",
                )
                if btn3.button("❌ Reddet", key=f"reject_{item['draft_id']}"):
                    apply_action(item["draft_id"], "rejected", reject_reason, "")
                    st.warning("Reddedildi.")
                    st.rerun()

                if btn4.button("🏷️ Eğitim Verisi", key=f"flag_{item['draft_id']}"):
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
                draft = db.query(RescueDraft).filter_by(id=r.draft_id).first()
                platform_badge = ""
                if draft:
                    platform_badge = " 🤖" if draft.platform == "reddit" else " 📱" if draft.platform == "telegram" else ""
                st.write(
                    f"**{r.action.upper()}**{platform_badge} — "
                    f"{r.reviewed_at.strftime('%Y-%m-%d %H:%M')} "
                    f"| Draft: `{r.draft_id[:8]}...`"
                )
                if r.editor_note:
                    st.caption(r.editor_note)
