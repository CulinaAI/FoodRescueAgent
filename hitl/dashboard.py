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

st.set_page_config(page_title="Food Rescue — Command Center", page_icon="🌿", layout="wide")
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
        st.error(f"Failed to post to Reddit: {exc}")
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


# ── Presentation ───────────────────────────────────────────────────────────────

_CSS = """
<style>
.block-container { padding-top: 2.1rem; padding-bottom: 3rem; max-width: 1240px; }

/* header */
.fr-header { display:flex; align-items:center; gap:14px; margin: 2px 0 10px; }
.fr-logo { font-size: 2.1rem; line-height: 1; }
.fr-title { font-size: 1.85rem; font-weight: 800; letter-spacing:-0.02em; margin:0; line-height:1.1;
            background: linear-gradient(90deg,#34D399,#10B981); -webkit-background-clip:text;
            background-clip:text; -webkit-text-fill-color:transparent; }
.fr-sub { color:#8B97A6; font-size:0.92rem; margin: 4px 0 0; display:flex; align-items:center; gap:10px; }
.fr-pill { display:inline-flex; align-items:center; gap:6px; font-size:0.74rem; font-weight:700;
           padding:3px 10px; border-radius:999px; letter-spacing:.02em; }
.fr-pill-live { background:rgba(239,68,68,.14); color:#F87171; border:1px solid rgba(239,68,68,.4); }
.fr-pill-dry  { background:rgba(52,211,153,.12); color:#34D399; border:1px solid rgba(52,211,153,.4); }

/* metric cards */
[data-testid="stMetric"] { background:#141B22; border:1px solid #232E39; border-radius:14px;
                           padding:14px 18px; }
[data-testid="stMetricValue"] { color:#E6EDF3; font-weight:700; }
[data-testid="stMetricLabel"] p { color:#8B97A6; font-weight:600; }

/* bordered containers read as cards */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }

/* badge row */
.fr-badges { display:flex; flex-wrap:wrap; gap:7px; align-items:center; margin:2px 0 10px; }
.fr-badge { font-size:0.73rem; font-weight:600; padding:3px 9px; border-radius:8px;
            border:1px solid #2A3641; background:#0F151B; color:#AEB9C7; }
.fr-badge-high { color:#F87171; border-color:rgba(239,68,68,.45); background:rgba(239,68,68,.08); }
.fr-badge-med  { color:#FBBF24; border-color:rgba(251,191,36,.45); background:rgba(251,191,36,.08); }
.fr-badge-low  { color:#34D399; border-color:rgba(52,211,153,.45); background:rgba(52,211,153,.08); }

/* field labels */
.fr-flabel { color:#8B97A6; font-size:0.72rem; font-weight:700; text-transform:uppercase;
             letter-spacing:.05em; margin:2px 0 4px; }

/* buttons */
.stButton > button { border-radius:10px; font-weight:600; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

_URGENCY_BADGE = {"high": "fr-badge-high", "medium": "fr-badge-med", "low": "fr-badge-low"}
_PLATFORM_LABEL = {"reddit": "🤖 Reddit", "telegram": "📱 Telegram", "manual": "✍️ Manual"}


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# header
if _REDDIT_POST_ENABLED and _REDDIT_CREDS_AVAILABLE:
    mode_pill = '<span class="fr-pill fr-pill-live">● LIVE — auto-post on</span>'
else:
    mode_pill = '<span class="fr-pill fr-pill-dry">● DRY-RUN — manual post</span>'

st.markdown(
    '<div class="fr-header"><span class="fr-logo">🌿</span><div>'
    '<p class="fr-title">Food Rescue — Command Center</p>'
    f'<p class="fr-sub">Human-in-the-loop moderation for AI rescue replies {mode_pill}</p>'
    '</div></div>',
    unsafe_allow_html=True,
)

stats = load_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Pending", stats["pending"])
c2.metric("Approved", stats["approved"])
c3.metric("Total reviews", stats["total_reviews"])
c4.metric("Reddit posts", stats["reddit_count"])

if not _REDDIT_CREDS_AVAILABLE:
    st.warning(
        "Missing Reddit credentials (REDDIT_CLIENT_ID / SECRET / USERNAME / PASSWORD). "
        "Approved Reddit replies are shown for manual posting — no auto-posting will occur."
    )

st.write("")
tab_pending, tab_history = st.tabs(["📋 Pending drafts", "📜 History"])

with tab_pending:
    platform_filter = st.radio(
        "Platform",
        ["all", "reddit", "telegram", "manual"],
        horizontal=True,
        label_visibility="collapsed",
        format_func=lambda x: {"all": "🌐 All", **_PLATFORM_LABEL}[x],
    )

    pending = load_pending(platform_filter)

    if not pending:
        st.success("No pending drafts — the queue is clear. 🎉")
    else:
        for item in pending:
            is_reddit = item["platform"] == "reddit"
            platform_badge = _PLATFORM_LABEL.get(item["platform"], "✍️ Manual")
            urgency = (item["urgency_hint"] or "unknown").lower()
            conf = item["confidence"]

            with st.container(border=True):
                # badge row
                ub = _URGENCY_BADGE.get(urgency, "fr-badge")
                badges = [f'<span class="fr-badge {ub}">{urgency.upper()}</span>',
                          f'<span class="fr-badge">{platform_badge}</span>']
                if item.get("subreddit"):
                    badges.append(f'<span class="fr-badge">r/{_esc(item["subreddit"])}</span>')
                badges.append(f'<span class="fr-badge">conf {conf:.2f}</span>')
                if item.get("created_at"):
                    badges.append(f'<span class="fr-badge">{item["created_at"].strftime("%H:%M")}</span>')
                st.markdown(f'<div class="fr-badges">{"".join(badges)}</div>', unsafe_allow_html=True)

                # Reddit context header
                if is_reddit and item.get("post_title"):
                    st.markdown(
                        f"**r/{item['subreddit']}** — "
                        + (f"[{item['post_title']}]({item['post_url']})" if item.get("post_url") else item["post_title"])
                    )

                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown('<p class="fr-flabel">Original message</p>', unsafe_allow_html=True)
                    st.text_area(
                        "Original message",
                        value=item["raw_text"],
                        height=160,
                        key=f"orig_{item['draft_id']}",
                        disabled=True,
                        label_visibility="collapsed",
                    )
                    if item["ingredients"]:
                        names = [i.get("name", "") for i in item["ingredients"]]
                        st.caption(f"🥗 Ingredients: {', '.join(names)}")

                    if is_reddit and item.get("post_url"):
                        st.link_button("🔗 Open in Reddit", item["post_url"])

                with col_right:
                    st.markdown('<p class="fr-flabel">Agent draft reply</p>', unsafe_allow_html=True)
                    draft_content = st.text_area(
                        "Agent draft reply",
                        value=item["content"],
                        height=160,
                        key=f"content_{item['draft_id']}",
                        label_visibility="collapsed",
                    )

                st.write("")
                btn1, btn2, btn3, btn4 = st.columns(4)

                approve_label = "✅ Approve" + (" + Reddit comment" if is_reddit and _REDDIT_CREDS_AVAILABLE else "")
                if btn1.button(approve_label, key=f"approve_{item['draft_id']}", use_container_width=True):
                    comment_id = apply_action(
                        item["draft_id"], "approved", "",
                        item["content"],
                        source_id=item.get("source_id"),
                        platform=item["platform"],
                    )
                    if is_reddit and comment_id:
                        st.success(f"Approved and posted to Reddit. Comment ID: `{comment_id}`")
                    elif is_reddit:
                        st.info("Approved (auto-post off/dry-run) — paste reply manually:")
                        st.code(item["content"])
                    else:
                        st.success("Approved!")
                    st.rerun()

                edit_label = "✏️ Edit & approve" + (" + Reddit" if is_reddit and _REDDIT_POST_ENABLED and _REDDIT_CREDS_AVAILABLE else "")
                if btn2.button(edit_label, key=f"edit_{item['draft_id']}", use_container_width=True):
                    comment_id = apply_action(
                        item["draft_id"], "edited", "Edited by moderator",
                        draft_content,
                        source_id=item.get("source_id"),
                        platform=item["platform"],
                    )
                    if is_reddit and comment_id:
                        st.success(f"Edited and posted to Reddit. Comment ID: `{comment_id}`")
                    elif is_reddit:
                        st.info("Edited (auto-post off/dry-run) — paste reply manually:")
                        st.code(draft_content)
                    else:
                        st.success("Edited and approved!")
                    st.rerun()

                if btn3.button("❌ Reject", key=f"reject_{item['draft_id']}", use_container_width=True):
                    apply_action(item["draft_id"], "rejected",
                                 st.session_state.get(f"reason_{item['draft_id']}", REJECT_REASONS[0]), "")
                    st.warning("Rejected.")
                    st.rerun()

                if btn4.button("🏷️ Training data", key=f"flag_{item['draft_id']}", use_container_width=True):
                    apply_action(item["draft_id"], "flagged", "Flagged for training", "")
                    st.info("Flagged as training data.")
                    st.rerun()

                st.selectbox(
                    "Reject reason",
                    REJECT_REASONS,
                    key=f"reason_{item['draft_id']}",
                )

with tab_history:
    with get_session() as db:
        reviews = (
            db.query(HitlReview)
            .order_by(HitlReview.reviewed_at.desc())
            .limit(100)
            .all()
        )
        if not reviews:
            st.info("No reviews yet.")
        else:
            _ACTION_ICON = {"approved": "✅", "edited": "✏️", "rejected": "❌", "flagged": "🏷️"}
            for r in reviews:
                draft = db.query(RescueDraft).filter_by(id=r.draft_id).first()
                platform_badge = ""
                if draft:
                    platform_badge = " 🤖" if draft.platform == "reddit" else " 📱" if draft.platform == "telegram" else ""
                icon = _ACTION_ICON.get(r.action, "•")
                st.write(
                    f"{icon} **{r.action.upper()}**{platform_badge} — "
                    f"{r.reviewed_at.strftime('%Y-%m-%d %H:%M')} "
                    f"· Draft `{r.draft_id[:8]}…`"
                )
                if r.editor_note:
                    st.caption(r.editor_note)
