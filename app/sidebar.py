import streamlit as st
from api.macros import extract_template_variables
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings

from app.api_utils import (
    API_BASE_URL,
    apply_macro_to_session,
    assign_session,
    auto_assign_session,
    create_macro,
    create_sla_policy,
    create_support_agent,
    create_webhook,
    delete_collection,
    delete_document,
    delete_documents,
    delete_macro,
    delete_session,
    delete_sessions,
    delete_sla_policy,
    delete_webhook,
    draft_article_from_session,
    evaluate_sla_alerts,
    export_session,
    get_agent_scorecards,
    get_agent_workload_analytics,
    get_business_hours_status,
    get_collection_analytics,
    get_collections_details,
    get_config,
    get_csat_summary,
    get_document_details,
    get_feedback_analytics,
    get_health,
    get_knowledge_analytics,
    get_metrics,
    get_quota,
    get_session_assignment_history,
    get_session_history,
    get_session_macro_suggestions,
    get_session_sla_status,
    get_sla_compliance_analytics,
    get_stats,
    get_support_triage_analytics,
    list_collections,
    list_documents,
    list_feedback,
    list_feedback_review_queue,
    list_knowledge_articles,
    list_knowledge_gaps,
    list_macro_categories,
    list_macros,
    list_sessions,
    list_sla_policies,
    list_support_agents,
    list_webhook_deliveries,
    list_webhooks,
    ping_webhook,
    publish_knowledge_article,
    rechunk_collection,
    rechunk_document,
    rename_collection,
    rename_session,
    render_macro,
    scan_knowledge_gaps,
    search_sessions,
    suggest_macros,
    summarize_session,
    update_feedback_review,
    update_knowledge_gap,
    update_session,
    update_support_agent,
    update_webhook,
    upload_document,
    upload_documents,
)

MODEL_OPTIONS = [model.value for model in ModelName]
AGENT_TIER_OPTIONS = ["tier_1", "tier_2", "tier_3"]
AGENT_TIER_LABELS = {
    "tier_1": "Tier 1: Frontline & Leasing Concierge",
    "tier_2": "Tier 2: Maintenance & Operations Specialist",
    "tier_3": "Tier 3: Property Leadership & Escalation Management",
}
TIER_BADGES = {
    "tier_1": "T1",
    "tier_2": "T2",
    "tier_3": "T3",
}
SESSION_STATUS_OPTIONS = ["active", "resolved", "escalated", "closed"]
SESSION_STATUS_FILTER_OPTIONS = ["All statuses", *SESSION_STATUS_OPTIONS]
SESSION_STATUS_ICONS = {
    "active": "🟢",
    "resolved": "✅",
    "escalated": "⚠️",
    "closed": "🔒",
}

SESSION_PRIORITY_OPTIONS = ["urgent", "high", "medium", "low"]
SESSION_PRIORITY_FILTER_OPTIONS = ["All priorities", *SESSION_PRIORITY_OPTIONS]
PRIORITY_BADGES = {
    "urgent": "🔴 [Urgent]",
    "high": "🟠 [High]",
    "medium": "🟡 [Med]",
    "low": "🔵 [Low]",
}
PRIORITY_EMOJIS = {
    "urgent": "🔴 Urgent",
    "high": "🟠 High",
    "medium": "🟡 Medium",
    "low": "🔵 Low",
}


def _init_config():
    if "config" not in st.session_state or st.session_state.config is None:
        st.session_state.config = get_config()
    return st.session_state.config


def get_model_options(config=None):
    if config and config.get("supported_models"):
        return list(config["supported_models"])
    return MODEL_OPTIONS


def get_default_model_index(options=None, config=None):
    if options is None:
        options = MODEL_OPTIONS
    if config and config.get("default_model"):
        default_model = config["default_model"]
    else:
        default_model = model_from_value(settings.default_model).value
    if default_model in options:
        return options.index(default_model)
    return 0


def _render_health_status():
    health = get_health()
    if health:
        st.sidebar.success(f"Backend: {health['status']} ({health['version']})")
    else:
        st.sidebar.error("Backend unavailable")

    biz_status = get_business_hours_status()
    if biz_status:
        if biz_status.get("is_open"):
            st.sidebar.markdown(
                "🟢 **Support Hours:** Open (Mon-Fri 09:00 - 18:00 UTC)"
            )
        else:
            next_open = biz_status.get("next_open_at")
            next_txt = f" (Opens: {next_open[:16].replace('T', ' ')})" if next_open else ""
            st.sidebar.markdown(
                f"🌙 **Support Hours:** Closed / After-Hours{next_txt}"
            )


def _render_reset_chat():
    if st.sidebar.button("Reset Chat"):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()


def _filter_sessions(sessions):
    queue_filter = st.sidebar.selectbox(
        "Queue view",
        options=["All sessions", "Unassigned only", "Escalated only (Tier 2/3)"],
        key="session_queue_filter",
    )
    if queue_filter == "Unassigned only":
        sessions = [s for s in sessions if not s.get("assigned_agent")]
    elif queue_filter == "Escalated only (Tier 2/3)":
        sessions = [
            s for s in sessions if s.get("escalation_tier") in ("tier_2", "tier_3")
        ]

    status_filter = st.sidebar.selectbox(
        "Filter by status",
        options=SESSION_STATUS_FILTER_OPTIONS,
        key="session_status_filter",
    )
    if status_filter != "All statuses":
        sessions = [s for s in sessions if (s.get("status") or "active") == status_filter]

    priority_filter = st.sidebar.selectbox(
        "Filter by priority",
        options=SESSION_PRIORITY_FILTER_OPTIONS,
        key="session_priority_filter",
    )
    if priority_filter != "All priorities":
        sessions = [s for s in sessions if (s.get("priority") or "medium") == priority_filter]

    search_query = st.sidebar.text_input(
        "Search conversations", key="session_search_query", placeholder="Filter by keyword..."
    )
    if not search_query.strip():
        return sessions
    search_hits = search_sessions(search_query.strip())
    matching_ids = {h["session_id"] for h in search_hits}
    return [s for s in sessions if s["session_id"] in matching_ids]


def _handle_session_actions(selected, new_label):
    rename_col, load_col, delete_col = st.sidebar.columns(3)
    if rename_col.button("Rename") and new_label.strip():
        with st.spinner("Renaming session..."):
            if rename_session(selected, new_label.strip()):
                st.session_state.sessions = list_sessions()
                st.rerun()
    if load_col.button("Load Session"):
        with st.spinner("Loading session..."):
            history = get_session_history(selected)
            st.session_state.session_id = selected
            st.session_state.messages = [
                {"role": m["role"], "content": m["content"]} for m in history
            ]
            st.rerun()
    if delete_col.button("Delete"):
        with st.spinner("Deleting session..."):
            if delete_session(selected):
                st.sidebar.success("Session deleted.")
                st.session_state.sessions = list_sessions()
                if st.session_state.session_id == selected:
                    st.session_state.session_id = None
                    st.session_state.messages = []
                st.session_state.pop("export_text", None)
                st.session_state.pop("export_session_id", None)
                st.rerun()


def _render_session_history():
    st.sidebar.header("Past Sessions")
    if st.sidebar.button("Refresh Sessions"):
        st.session_state.sessions = list_sessions()

    if "sessions" not in st.session_state:
        st.session_state.sessions = list_sessions()

    sessions = st.session_state.sessions
    if not sessions:
        st.sidebar.caption("No past sessions yet.")
        return

    sessions = _filter_sessions(sessions)
    if not sessions:
        st.sidebar.caption("No matching conversations found.")
        return

    labels = {"(current)": "(current)"}
    for session in sessions:
        title = session.get("label") or session.get("preview") or session["session_id"][:8]
        status = session.get("status") or "active"
        icon = SESSION_STATUS_ICONS.get(status, "🟢")
        prio = session.get("priority") or "medium"
        prio_badge = f" {PRIORITY_BADGES.get(prio, '')}" if prio != "medium" else ""
        tier = session.get("escalation_tier") or "tier_1"
        tier_tag = f" [{TIER_BADGES.get(tier, 'T1')}]"
        assigned = session.get("assigned_agent")
        assigned_tag = f" (@{assigned})" if assigned else " (Unassigned)"
        tags = session.get("tags") or []
        tags_str = f" [{', '.join(tags)}]" if tags else ""
        msg_cnt = session["message_count"]
        labels[session["session_id"]] = (
            f"{icon}{prio_badge}{tier_tag} {title} ({msg_cnt} msgs){assigned_tag}{tags_str}"
        )

    bulk_delete = st.sidebar.checkbox(
        "Bulk delete sessions", value=False, key="bulk_delete_sessions_mode"
    )
    if bulk_delete:
        to_delete = st.sidebar.multiselect(
            "Select sessions to delete",
            options=[s["session_id"] for s in sessions],
            format_func=lambda sid: labels.get(sid, sid),
            key="bulk_delete_session_ids",
        )
        if st.sidebar.button("Delete Selected Sessions") and to_delete:
            with st.spinner("Deleting sessions..."):
                res = delete_sessions(to_delete)
                if res and res.get("deleted", 0) > 0:
                    st.sidebar.success(f"Deleted {res['deleted']} session(s).")
                    st.session_state.sessions = list_sessions()
                    if st.session_state.session_id in to_delete:
                        st.session_state.session_id = None
                        st.session_state.messages = []
                    if st.session_state.get("export_session_id") in to_delete:
                        st.session_state.pop("export_text", None)
                        st.session_state.pop("export_session_id", None)
                    st.rerun()
                else:
                    st.sidebar.error("Failed to delete sessions.")
        return

    options = ["(current)"] + [s["session_id"] for s in sessions]
    selected = st.sidebar.selectbox(
        "Open a session",
        options=options,
        format_func=lambda session_id: labels.get(session_id, session_id),
        key="session_picker",
    )
    if selected == "(current)":
        return
    new_label = st.sidebar.text_input("Rename session", key="rename_session", max_chars=80)
    _handle_session_actions(selected, new_label)
    _render_session_metadata(selected, sessions)
    _render_session_export(selected)


def _render_session_assignment_controls(selected, current):
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 👤 Agent Assignment & Tier")
    curr_agent = current.get("assigned_agent") if current else None
    curr_tier = (current.get("escalation_tier") or "tier_1") if current else "tier_1"

    all_agents = list_support_agents() or []
    agent_choices = ["(Unassigned)"] + [a["agent_id"] for a in all_agents]
    agent_display_names = {"(Unassigned)": "Unassigned"}
    for a in all_agents:
        agent_display_names[a["agent_id"]] = (
            f"{a['name']} ({a['tier'].upper()} - {a['department']})"
        )

    agent_idx = 0
    if curr_agent and curr_agent in agent_choices:
        agent_idx = agent_choices.index(curr_agent)

    selected_agent = st.sidebar.selectbox(
        "Assigned Agent",
        options=agent_choices,
        index=agent_idx,
        format_func=lambda x: agent_display_names.get(x, x),
        key=f"assign_agent_select_{selected}",
    )

    tier_idx = (
        AGENT_TIER_OPTIONS.index(curr_tier) if curr_tier in AGENT_TIER_OPTIONS else 0
    )
    selected_tier = st.sidebar.selectbox(
        "Escalation Tier",
        options=AGENT_TIER_OPTIONS,
        index=tier_idx,
        format_func=lambda t: AGENT_TIER_LABELS.get(t, t),
        key=f"escalation_tier_select_{selected}",
    )

    assign_col1, assign_col2 = st.sidebar.columns(2)
    if assign_col1.button("Assign / Route", key=f"btn_manual_assign_{selected}"):
        with st.spinner("Updating assignment..."):
            target_agent = None if selected_agent == "(Unassigned)" else selected_agent
            res = assign_session(
                selected,
                agent_id=target_agent,
                tier=selected_tier,
                reason="Manual assignment in sidebar UI",
                assigned_by="operator",
            )
            if res:
                st.sidebar.success("Assigned successfully!")
                st.session_state.sessions = list_sessions()
                st.rerun()
            else:
                st.sidebar.error("Failed to update assignment.")

    if assign_col2.button("⚡ Auto-Assign", key=f"btn_auto_assign_{selected}"):
        with st.spinner("Running auto-assignment routing..."):
            res = auto_assign_session(
                selected,
                target_tier=selected_tier,
                assigned_by="auto_router",
            )
            if res and res.get("assigned_agent"):
                agent_name = res["assigned_agent"]
                tier_val = res.get("escalation_tier")
                st.sidebar.success(f"Assigned to {agent_name} ({tier_val})")
                st.session_state.sessions = list_sessions()
                st.rerun()
            else:
                st.sidebar.warning("No eligible active agent found for this tier.")

    _render_session_assignment_history(selected)


def _render_session_assignment_history(selected):
    with st.sidebar.expander("📜 Assignment Audit History"):
        history = get_session_assignment_history(selected)
        if not history:
            st.caption("No assignment events recorded.")
            return

        for item in history[:5]:
            from_ag = item.get("from_agent_id") or "None"
            to_ag = item.get("to_agent_id") or "Unassigned"
            t_label = item.get("escalation_tier")
            tier_info = f"[{t_label}]" if t_label else ""
            ts = (item.get("assigned_at") or "")[:19].replace("T", " ")
            st.markdown(f"**{ts}** {tier_info}")
            assigned_by = item.get("assigned_by") or "system"
            st.caption(f"{from_ag} ➔ **{to_ag}** ({assigned_by})")
            if item.get("reason"):
                st.caption(f"_{item['reason']}_")
            st.markdown("---")


def _render_session_metadata(selected, sessions):
    current = next((s for s in sessions if s.get("session_id") == selected), None)
    curr_status = (current.get("status") or "active") if current else "active"
    status_idx = (
        SESSION_STATUS_OPTIONS.index(curr_status)
        if curr_status in SESSION_STATUS_OPTIONS
        else 0
    )
    new_status = st.sidebar.selectbox(
        "Session status",
        options=SESSION_STATUS_OPTIONS,
        index=status_idx,
        key=f"session_status_{selected}",
    )

    curr_prio = (current.get("priority") or "medium") if current else "medium"
    prio_idx = (
        SESSION_PRIORITY_OPTIONS.index(curr_prio)
        if curr_prio in SESSION_PRIORITY_OPTIONS
        else 2
    )
    new_priority = st.sidebar.selectbox(
        "Session priority",
        options=SESSION_PRIORITY_OPTIONS,
        index=prio_idx,
        format_func=lambda p: PRIORITY_EMOJIS.get(p, p.title()),
        key=f"session_priority_{selected}",
    )

    raw_tags = current.get("tags") if current else ""
    if isinstance(raw_tags, list):
        curr_tags = ", ".join(raw_tags)
    elif isinstance(raw_tags, str):
        curr_tags = raw_tags
    else:
        curr_tags = ""

    new_tags_str = st.sidebar.text_input(
        "Tags (comma-separated)",
        value=curr_tags,
        key=f"session_tags_{selected}",
        placeholder="e.g. billing, urgent",
    )

    curr_summary = current.get("summary") if current else None
    if curr_summary:
        st.sidebar.caption(f"**Summary:** {curr_summary}")

    if st.sidebar.button("Auto-Summarize Dialogue", key=f"btn_summarize_{selected}"):
        with st.spinner("Summarizing dialogue..."):
            summary_res = summarize_session(selected, save_summary=True)
            if summary_res:
                st.sidebar.success("Session summarized!")
                if summary_res.get("sentiment"):
                    st.sidebar.info(f"Sentiment: {summary_res['sentiment']}")
                st.session_state.sessions = list_sessions()
                st.rerun()
            else:
                st.sidebar.error("Failed to summarize session.")

    curr_notes = (current.get("resolution_notes") or "") if current else ""
    new_notes = st.sidebar.text_area(
        "Resolution Notes",
        value=curr_notes,
        key=f"session_notes_{selected}",
        placeholder="Add resolution or follow-up notes...",
    )

    _render_session_metadata_actions(
        selected, new_status, new_priority, new_tags_str, new_notes
    )
    _render_session_assignment_controls(selected, current)
    _render_session_sla_card(selected)


def _render_session_metadata_actions(
    selected,
    new_status,
    new_priority,
    new_tags_str,
    new_notes,
):
    col_meta1, col_meta2 = st.sidebar.columns(2)
    with col_meta1:
        if st.button("Update Metadata", key=f"btn_update_meta_{selected}"):
            tag_list = [t.strip() for t in new_tags_str.split(",") if t.strip()]
            with st.spinner("Updating session metadata..."):
                if update_session(
                    selected,
                    status=new_status,
                    priority=new_priority,
                    tags=tag_list,
                    resolution_notes=new_notes.strip() if new_notes.strip() else None,
                ):
                    st.sidebar.success("Session metadata updated.")
                    st.session_state.sessions = list_sessions()
                    st.rerun()
                else:
                    st.sidebar.error("Failed to update session metadata.")

    with col_meta2:
        if st.button("📝 Draft Article", key=f"btn_draft_kb_{selected}"):
            with st.spinner("Drafting FAQ article..."):
                draft = draft_article_from_session(selected)
                if draft:
                    st.sidebar.success(f"Article #{draft['id']} drafted!")
                    st.rerun()


def _render_session_sla_card(selected):
    sla_info = get_session_sla_status(selected)
    if not sla_info:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⏱️ SLA Status")
    breach_status = sla_info.get("breach_status", "healthy")
    policy_name = sla_info.get("policy_name") or "Standard Policy"
    st.sidebar.caption(f"**Policy:** {policy_name}")

    if breach_status == "breached":
        st.sidebar.error("🚨 **SLA Breached**")
    elif breach_status == "approaching_breach":
        st.sidebar.warning("⚠️ **Approaching Breach (<30m)**")
    elif breach_status == "met":
        st.sidebar.success("✅ **SLA Met**")
    else:
        st.sidebar.info("⏱️ **SLA Healthy**")

    resp_rem = sla_info.get("minutes_to_response_deadline")
    resp_text = (
        f"{resp_rem:.0f}m remaining"
        if resp_rem is not None and resp_rem > 0
        else ("Met" if sla_info.get("response_met") else "Overdue")
    )
    resol_rem = sla_info.get("minutes_to_resolution_deadline")
    resol_text = (
        f"{resol_rem:.0f}m remaining"
        if resol_rem is not None and resol_rem > 0
        else ("Resolved" if sla_info.get("resolution_met") else "Overdue")
    )

    col1, col2 = st.sidebar.columns(2)
    col1.metric("First Response", resp_text)
    col2.metric("Resolution", resol_text)


EXPORT_FORMAT_META = {
    "markdown": {"ext": ".md", "mime": "text/markdown", "label": "Markdown (.md)"},
    "json": {"ext": ".json", "mime": "application/json", "label": "JSON (.json)"},
    "csv": {"ext": ".csv", "mime": "text/csv", "label": "CSV (.csv)"},
}


def get_export_formats(config=None):
    if config and config.get("supported_export_formats"):
        return list(config["supported_export_formats"])
    return list(EXPORT_FORMAT_META.keys())


def _render_session_export(selected):
    config = st.session_state.get("config")
    formats = get_export_formats(config)
    selected_format = st.sidebar.selectbox(
        "Export format",
        options=formats,
        format_func=lambda fmt: EXPORT_FORMAT_META.get(fmt, {}).get("label", fmt),
        key="export_format_selector",
    )
    if st.sidebar.button("Prepare Export"):
        with st.spinner("Preparing export..."):
            try:
                text = export_session(selected, format=selected_format)
            except TypeError:
                text = export_session(selected)
            if text is not None:
                st.session_state.export_text = text
                st.session_state.export_session_id = selected
                st.session_state.export_format = selected_format
    if st.session_state.get("export_session_id") == selected and st.session_state.get(
        "export_text"
    ):
        active_fmt = st.session_state.get("export_format", "markdown")
        meta = EXPORT_FORMAT_META.get(
            active_fmt, {"ext": ".md", "mime": "text/markdown", "label": "Markdown"}
        )
        ext = meta["ext"]
        mime = meta["mime"]
        st.sidebar.download_button(
            f"Download ({ext})",
            data=st.session_state.export_text,
            file_name=f"{selected}{ext}",
            mime=mime,
            key="download_export",
        )


def _render_model_selector():
    config = st.session_state.get("config")
    options = get_model_options(config)
    default_idx = get_default_model_index(options, config)
    st.sidebar.selectbox(
        "Select Model", options=options, index=default_idx, key="model"
    )


ALL_COLLECTIONS = "All collections"


def _render_collection_picker():
    st.sidebar.header("Collection")
    if st.sidebar.button("Refresh Collections"):
        st.session_state.collections = list_collections()

    if "collections" not in st.session_state:
        st.session_state.collections = list_collections()

    known = st.session_state.collections or ["default"]
    options = [ALL_COLLECTIONS] + [c for c in known if c != ALL_COLLECTIONS]
    selected = st.sidebar.selectbox("Active collection", options=options, key="collection_picker")
    active = None if selected == ALL_COLLECTIONS else selected
    if st.session_state.get("docs_collection") != active:
        st.session_state.documents = list_documents(active)
        st.session_state.docs_collection = active
        st.session_state.selected_doc_ids = []
    st.session_state.active_collection = active
    if active and active != "default":
        new_name = st.sidebar.text_input(
            "Rename collection", key="rename_collection", placeholder="e.g. clients-globex"
        )
        rename_col, delete_col = st.sidebar.columns(2)
        if rename_col.button("Rename") and new_name.strip():
            with st.spinner("Renaming collection..."):
                renamed = rename_collection(active, new_name.strip())
                if renamed:
                    st.sidebar.success(f"Renamed to '{renamed['collection']}'.")
                    st.session_state.collections = list_collections()
                    st.session_state.documents = list_documents(renamed["collection"])
                    st.session_state.docs_collection = renamed["collection"]
                    st.session_state.active_collection = renamed["collection"]
                    st.rerun()
        if delete_col.button("Delete"):
            with st.spinner("Deleting collection..."):
                if delete_collection(active):
                    st.sidebar.success(f"Collection '{active}' deleted.")
                    st.session_state.collections = list_collections()
                    st.session_state.documents = list_documents(None)
                    st.session_state.docs_collection = None
                    st.session_state.active_collection = None
                    st.rerun()
    return active


def _render_collection_insights(active_collection):
    """Render collection metadata and chunk distribution statistics."""
    if not active_collection:
        return
    with st.sidebar.expander("Collection Insights"):
        try:
            details = get_collections_details()
            collection_detail = next(
                (d for d in details if d["collection"] == active_collection), None
            )
            if not collection_detail:
                st.caption("No details available.")
                return
            st.metric("Documents", collection_detail.get("document_count", 0))
            st.metric("Chunks", collection_detail.get("chunk_count", 0))

            analytics = get_collection_analytics(active_collection)
            if analytics and analytics.get("total_chunks", 0) > 0:
                avg_len = analytics.get("avg_chunk_length", 0)
                st.metric("Avg Chunk Length", f"{avg_len:.0f} chars")
                min_len = analytics.get("min_chunk_length", 0)
                max_len = analytics.get("max_chunk_length", 0)
                st.caption(f"Min / Max chunk size: {min_len} / {max_len} chars")

                strategies = analytics.get("strategy_distribution", {})
                if strategies:
                    strat_pills = " · ".join(
                        f"{k}: {v}" for k, v in sorted(strategies.items())
                    )
                    st.caption(f"Strategies: {strat_pills}")

                histogram = analytics.get("length_histogram", {})
                if histogram and any(v > 0 for v in histogram.values()):
                    st.caption("Length distribution:")
                    for bucket, count in histogram.items():
                        if count > 0:
                            st.write(f"  {bucket} chars: {count}")

            file_formats = collection_detail.get("file_formats", {})
            if file_formats:
                st.caption("File formats:")
                for fmt, count in file_formats.items():
                    st.write(f"  {fmt}: {count}")
            earliest = collection_detail.get("earliest_upload")
            latest = collection_detail.get("latest_upload")
            if earliest:
                st.caption(f"First upload: {earliest}")
            if latest:
                st.caption(f"Last upload: {latest}")
        except Exception as e:
            st.caption(f"Error loading collection details: {e}")


def _render_batch_rechunk(active_collection):
    """Render batch collection re-chunking controls in the sidebar."""
    if not active_collection:
        return
    with st.sidebar.expander("Batch Re-chunk Collection"):
        rechunk_strategy_options = ["recursive", "semantic", "markdown"]
        col_strat = st.selectbox(
            "Collection Strategy",
            options=rechunk_strategy_options,
            index=0,
            format_func=lambda s: s.capitalize(),
            key=f"batch_rechunk_strat_{active_collection}",
        )
        col_size = st.number_input(
            "Batch Chunk Size",
            min_value=100,
            max_value=4000,
            value=1000,
            step=50,
            key=f"batch_rechunk_size_{active_collection}",
        )
        max_col_overlap = max(0, int(col_size) - 1)
        col_overlap = st.number_input(
            "Batch Chunk Overlap",
            min_value=0,
            max_value=max_col_overlap,
            value=min(200, max_col_overlap),
            step=20,
            key=f"batch_rechunk_overlap_{active_collection}",
        )
        if st.button("Re-chunk Entire Collection", key=f"btn_batch_rechunk_{active_collection}"):
            with st.spinner(f"Re-chunking all documents in '{active_collection}'..."):
                res = rechunk_collection(
                    active_collection,
                    chunking_strategy=col_strat,
                    chunk_size=int(col_size),
                    chunk_overlap=int(col_overlap),
                )
                if res:
                    msg = (
                        f"Collection '{active_collection}' re-chunked: "
                        f"{res.get('rechunked_documents', 0)} re-chunked, "
                        f"{res.get('skipped_documents', 0)} skipped."
                    )
                    st.success(msg)
                    st.session_state.documents = list_documents(active_collection)
                    st.rerun()
                else:
                    st.error("Batch re-chunking failed.")


def _render_ops_metrics():
    st.sidebar.header("Backend Metrics")
    metrics = get_metrics()
    if not metrics:
        st.sidebar.caption("Metrics unavailable.")
        return

    stats = get_stats()
    if stats:
        st.sidebar.caption(
            f"Library: {stats.get('documents', 0)} docs · "
            f"{stats.get('collections', 0)} collections · "
            f"{stats.get('sessions', 0)} sessions"
        )

    requests_total = (
        metrics.get("chat_requests", 0)
        + metrics.get("stream_requests", 0)
        + metrics.get("uploads", 0)
        + metrics.get("deletes", 0)
    )
    errors_total = metrics.get("chat_errors", 0) + metrics.get("upload_errors", 0)
    st.sidebar.metric("Requests", requests_total)
    st.sidebar.metric("Errors", errors_total)
    st.sidebar.metric("Prompt tokens (est.)", metrics.get("prompt_tokens_est", 0))
    st.sidebar.metric("Completion tokens (est.)", metrics.get("completion_tokens_est", 0))

    quota = get_quota()
    if quota and not quota.get("unlimited", True):
        st.sidebar.metric(
            "Daily token quota left (est.)",
            quota.get("remaining", 0),
            delta=None,
        )

    with st.sidebar.expander("Latency averages (s)"):
        latency_keys = sorted(key for key in metrics if key.startswith("latency_avg_seconds_"))
        if not latency_keys:
            st.caption("No latency data yet.")
        for key in latency_keys:
            group = key.removeprefix("latency_avg_seconds_")
            st.write(f"{group}: {metrics[key]}")


def _render_upload_document(active_collection):
    st.sidebar.header("Upload Document")
    config = st.session_state.get("config")
    if config and "max_upload_size_bytes" in config:
        max_mb = config["max_upload_size_bytes"] // (1024 * 1024)
    else:
        max_mb = settings.max_upload_mb
    max_files = (
        config.get("max_bulk_upload_files", settings.max_bulk_files)
        if config
        else settings.max_bulk_files
    )
    st.sidebar.caption(f"Max {max_mb} MB per file · Up to {max_files} files per batch")
    uploaded_files = st.sidebar.file_uploader(
        "Choose file(s)",
        type=["pdf", "docx", "html", "md", "txt", "csv"],
        accept_multiple_files=True,
    )
    new_collection = st.sidebar.text_input(
        "New collection (optional)", key="new_collection", placeholder="e.g. clients-acme"
    )
    if uploaded_files and st.sidebar.button("Upload"):
        if len(uploaded_files) > max_files:
            st.sidebar.error(f"Cannot upload more than {max_files} files at once.")
            return
        target = (new_collection or "").strip() or active_collection or "default"
        with st.spinner("Uploading..."):
            if len(uploaded_files) == 1:
                upload_response = upload_document(uploaded_files[0], target)
                if upload_response:
                    st.sidebar.success(
                        f"File '{uploaded_files[0].name}' uploaded successfully with ID "
                        f"{upload_response['file_id']}."
                    )
            else:
                bulk_response = upload_documents(uploaded_files, target)
                if bulk_response:
                    st.sidebar.success(
                        f"Uploaded {bulk_response['uploaded']} of "
                        f"{bulk_response['uploaded'] + bulk_response['failed']} files."
                    )
                    for item in bulk_response["results"]:
                        if item["status"] == "error":
                            st.sidebar.error(f"{item['filename']}: {item['detail']}")
            st.session_state.collections = list_collections()
            st.session_state.documents = list_documents(active_collection)


def _render_refresh_documents(active_collection):
    st.sidebar.header("Uploaded Documents")
    if st.sidebar.button("Refresh Document List"):
        with st.spinner("Refreshing..."):
            st.session_state.documents = list_documents(active_collection)

    if "documents" not in st.session_state:
        st.session_state.documents = list_documents(active_collection)


def _render_document_list():
    documents = st.session_state.documents
    if not documents:
        return

    for doc in documents:
        st.sidebar.markdown(
            f"**{doc['filename']}**  \nID: `{doc['id']}`  \nCollection: "
            f"`{doc.get('collection', 'default')}`  \nUploaded: `{doc['upload_timestamp']}`"
        )

    bulk_delete = st.sidebar.checkbox(
        "Bulk delete mode", value=False, key="bulk_delete_mode"
    )
    if bulk_delete:
        to_delete = st.sidebar.multiselect(
            "Select documents to delete",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
            key="bulk_delete_ids",
        )
        if st.sidebar.button("Delete Selected Documents") and to_delete:
            with st.spinner("Deleting documents..."):
                res = delete_documents(to_delete)
                if res and res.get("deleted", 0) > 0:
                    st.sidebar.success(f"Deleted {res['deleted']} document(s).")
                    st.session_state.documents = list_documents(
                        st.session_state.get("active_collection")
                    )
                    st.rerun()
                else:
                    st.sidebar.error("Failed to delete documents.")
    else:
        selected_file_id = st.sidebar.selectbox(
            "Select a document to delete",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
        )
        if st.sidebar.button("Delete Selected Document"):
            with st.spinner("Deleting..."):
                delete_response = delete_document(selected_file_id)
                if delete_response:
                    st.sidebar.success(f"Document with ID {selected_file_id} deleted successfully.")
                    st.session_state.documents = list_documents(
                        st.session_state.get("active_collection")
                    )
                else:
                    st.sidebar.error(f"Failed to delete document with ID {selected_file_id}.")


def _render_document_inspector():
    documents = st.session_state.get("documents", [])
    if not documents:
        return
    with st.sidebar.expander("Inspect Document Chunks"):
        inspect_id = st.selectbox(
            "Select document to inspect",
            options=[doc["id"] for doc in documents],
            format_func=lambda x: next(doc["filename"] for doc in documents if doc["id"] == x),
            key="inspect_doc_id",
        )
        if st.button("Load Details", key="load_doc_details"):
            with st.spinner("Loading chunks..."):
                details = get_document_details(inspect_id)
                st.session_state["inspect_doc_details"] = details

        details = st.session_state.get("inspect_doc_details")
        if details and details.get("id") == inspect_id:
            st.markdown(f"**Total chunks:** `{details.get('chunk_count', 0)}`")
            if details.get("chunking_strategy"):
                strategy_label = str(details["chunking_strategy"]).capitalize()
                chunk_size = details.get("chunk_size", 1000)
                chunk_overlap = details.get("chunk_overlap", 200)
                st.markdown(
                    f"**Strategy:** `{strategy_label}`  \n"
                    f"**Chunk size:** `{chunk_size}` | **Overlap:** `{chunk_overlap}`"
                )
            if details.get("sha256"):
                st.caption(f"SHA-256: `{details['sha256'][:16]}...`")

            # Re-chunking controls
            rechunk_strategy_options = ["recursive", "semantic", "markdown"]
            current_strat = details.get("chunking_strategy") or "recursive"
            strat_idx = (
                rechunk_strategy_options.index(current_strat)
                if current_strat in rechunk_strategy_options
                else 0
            )
            new_strat = st.selectbox(
                "Re-chunk Strategy",
                options=rechunk_strategy_options,
                index=strat_idx,
                format_func=lambda s: s.capitalize(),
                key=f"rechunk_strat_{inspect_id}",
            )
            new_size = st.number_input(
                "Re-chunk Size",
                min_value=100,
                max_value=4000,
                value=int(details.get("chunk_size") or 1000),
                step=50,
                key=f"rechunk_size_{inspect_id}",
            )
            max_overlap = max(0, int(new_size) - 1)
            current_overlap = min(int(details.get("chunk_overlap") or 200), max_overlap)
            new_overlap = st.number_input(
                "Re-chunk Overlap",
                min_value=0,
                max_value=max_overlap,
                value=current_overlap,
                step=20,
                key=f"rechunk_overlap_{inspect_id}",
            )
            if st.button("Apply Re-chunk", key=f"rechunk_btn_{inspect_id}"):
                with st.spinner("Re-chunking document..."):
                    updated = rechunk_document(
                        inspect_id,
                        chunking_strategy=new_strat,
                        chunk_size=int(new_size),
                        chunk_overlap=int(new_overlap),
                    )
                    if updated:
                        st.session_state["inspect_doc_details"] = updated
                        st.success("Document re-chunked successfully!")
                        st.rerun()

            for chunk in details.get("chunks", [])[:10]:
                pg = f", p.{chunk['page']}" if chunk.get("page") else ""
                score = chunk.get("score")
                score_badge = f" (score: {score:.3f})" if score is not None else ""
                st.caption(f"Chunk {chunk['chunk_index']}{pg}{score_badge}:")
                st.text(chunk.get("preview", ""))


def _render_retrieval_filters():
    st.sidebar.header("Retrieval Filters")
    documents = st.session_state.get("documents", [])
    if not documents:
        st.session_state.selected_doc_ids = []
        st.sidebar.caption("No documents in the active collection.")
        st.sidebar.checkbox("Hybrid search (BM25 + vector)", value=False, key="use_hybrid")
        st.sidebar.checkbox(
    "Cross-encoder rerank (semantic)", value=False, key="use_cross_encoder_rerank"
)
        return
    st.sidebar.multiselect(
        "Restrict to document(s)",
        options=[doc["id"] for doc in documents],
        default=[],
        format_func=lambda doc_id: next(
            doc["filename"] for doc in documents if doc["id"] == doc_id
        ),
        key="selected_doc_ids",
    )
    st.sidebar.checkbox("Hybrid search (BM25 + vector)", value=False, key="use_hybrid")
    st.sidebar.checkbox(
    "Cross-encoder rerank (semantic)", value=False, key="use_cross_encoder_rerank"
)


def _render_feedback_analytics():
    with st.sidebar.expander("Feedback Analytics"):
        try:
            analytics = get_feedback_analytics(recent_comments_limit=3)
            total = analytics.get("total_feedback", 0)
            positive = analytics.get("positive_feedback", 0)
            negative = analytics.get("negative_feedback", 0)
            satisfaction = analytics.get("satisfaction_rate", 0.0)
            comment_rate = analytics.get("comment_rate", 0.0)
            recent = analytics.get("recent_comments", [])

            st.metric("Satisfaction Rate", f"{satisfaction:.1f}%")
            col1, col2 = st.columns(2)
            col1.metric("👍 Positive", positive)
            col2.metric("👎 Negative", negative)

            st.caption(f"Total feedback: {total} · Comment rate: {comment_rate:.1f}%")

            if recent:
                st.caption("Recent comments:")
                for item in recent:
                    icon = "👍" if item.get("rating") == 1 else "👎"
                    sid = item.get("session_id", "")[:8]
                    comment = item.get("comment")
                    if comment:
                        st.markdown(f"{icon} `{sid}`: \"{comment[:50]}...\"")
        except Exception as e:
            st.caption(f"Error loading analytics: {e}")


def _render_feedback_review():
    with st.sidebar.expander("Feedback Review"):
        rating_filter_label = st.selectbox(
            "Filter by rating",
            options=["All", "Positive (👍)", "Negative (👎)"],
            key="feedback_rating_filter",
        )
        rating_filter = None
        if rating_filter_label == "Positive (👍)":
            rating_filter = 1
        elif rating_filter_label == "Negative (👎)":
            rating_filter = -1

        if st.button("Refresh Feedback", key="refresh_feedback_btn"):
            st.session_state.feedback_data = list_feedback(rating=rating_filter, limit=20)

        if (
            "feedback_data" not in st.session_state
            or st.session_state.get("feedback_filter") != rating_filter
        ):
            st.session_state.feedback_data = list_feedback(rating=rating_filter, limit=20)
            st.session_state.feedback_filter = rating_filter

        data = st.session_state.get("feedback_data")
        if not data or not data.get("items"):
            st.caption("No feedback recorded yet.")
            return

        items = data["items"]
        total = data.get("total", len(items))
        st.caption(f"Showing {len(items)} of {total} feedback entries")

        for item in items:
            icon = "👍" if item.get("rating") == 1 else "👎"
            sid = item.get("session_id", "")
            sid_short = sid[:8]
            created = item.get("created_at", "")
            comment = item.get("comment")
            comment_text = f'"{comment}"' if comment else "*(no comment)*"
            st.markdown(f"**{icon} {sid_short}** ({created})  \n{comment_text}")
            if st.button(f"Open {sid_short}", key=f"open_fb_{item['id']}"):
                with st.spinner("Loading session..."):
                    history = get_session_history(sid)
                    st.session_state.session_id = sid
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"]} for m in history
                    ]
                    st.rerun()


def _render_support_triage_analytics():
    with st.sidebar.expander("Support Triage Analytics"):
        try:
            analytics = get_support_triage_analytics()
            if not analytics:
                st.caption("No triage analytics available.")
                return
            total = analytics.get("total_sessions", 0)
            res_rate = analytics.get("resolution_rate", 0.0)
            esc_rate = analytics.get("escalation_rate", 0.0)
            avg_turns = analytics.get("avg_turns_per_session", 0.0)

            col1, col2 = st.columns(2)
            col1.metric("Total Sessions", total)
            col2.metric("Resolution Rate", f"{res_rate:.1f}%")

            col3, col4 = st.columns(2)
            col3.metric("Escalation Rate", f"{esc_rate:.1f}%")
            col4.metric("Avg Turns", f"{avg_turns:.1f}")

            active = analytics.get("active_count", 0)
            resolved = analytics.get("resolved_count", 0)
            escalated = analytics.get("escalated_count", 0)
            closed = analytics.get("closed_count", 0)
            st.caption(
                f"🟢 Active: {active} · ✅ Resolved: {resolved} · "
                f"⚠️ Escalated: {escalated} · 🔒 Closed: {closed}"
            )

            top_tags = analytics.get("top_tags", [])
            if top_tags:
                tag_badges = " ".join([f"`{t['tag']}` ({t['count']})" for t in top_tags[:5]])
                st.markdown(f"**Top Tags:** {tag_badges}")
        except Exception as e:
            st.caption(f"Error loading triage analytics: {e}")


def _render_webhook_subscriptions():
    st.markdown("##### Subscriptions")
    hooks = list_webhooks()
    if not hooks:
        st.caption("No webhooks registered.")
        return

    for wh in hooks:
        wid = wh["id"]
        active_icon = "🟢" if wh.get("is_active") else "⚪"
        events_pill = wh.get("events", "*")
        failures = wh.get("failure_count", 0)
        fail_badge = f" · ⚠️ {failures} fails" if failures > 0 else ""
        st.markdown(
            f"**#{wid}** {active_icon} `{events_pill}`{fail_badge}  \n"
            f"`{wh['url']}`"
        )

        col1, col2, col3 = st.columns(3)
        if col1.button("Ping", key=f"ping_wh_{wid}"):
            res = ping_webhook(wid)
            if res and res.get("success"):
                st.success("Ping delivered!")
            else:
                err = res.get("error") if res else "Failed"
                st.error(f"Ping failed: {err}")

        toggle_label = "Disable" if wh.get("is_active") else "Enable"
        if col2.button(toggle_label, key=f"toggle_wh_{wid}"):
            update_webhook(wid, is_active=not wh.get("is_active"))
            st.rerun()

        if col3.button("Delete", key=f"del_wh_{wid}") and delete_webhook(wid):
            st.success("Deleted!")
            st.rerun()


def _render_webhook_register():
    st.markdown("---")
    st.markdown("##### Register Webhook")
    new_url = st.text_input(
        "Webhook URL",
        key="new_webhook_url",
        placeholder="https://example.com/alerts",
    )
    new_events = st.text_input(
        "Events (*, session.escalated, ...)",
        value="*",
        key="new_webhook_events",
    )
    new_secret = st.text_input(
        "Secret (HMAC-SHA256)",
        type="password",
        key="new_webhook_secret",
    )
    new_active = st.checkbox("Active", value=True, key="new_webhook_active")

    if st.button("Register Webhook", key="submit_new_webhook"):
        if not new_url.strip():
            st.error("Webhook URL is required.")
            return
        created = create_webhook(
            url=new_url.strip(),
            events=new_events.strip() or "*",
            secret=new_secret.strip() if new_secret else None,
            is_active=new_active,
        )
        if created:
            st.success(f"Webhook #{created['id']} registered!")
            st.rerun()


def _render_webhook_audit_log():
    st.markdown("---")
    st.markdown("##### Recent Deliveries")
    deliveries_data = list_webhook_deliveries(limit=5)
    items = deliveries_data.get("items", []) if deliveries_data else []
    if not items:
        st.caption("No delivery logs yet.")
        return

    for log in items:
        status_icon = "✅" if log.get("success") else "❌"
        code = log.get("status_code") or "ERR"
        st.markdown(
            f"{status_icon} **{log.get('event')}** (HTTP {code})  \n"
            f"`{log.get('url')}`"
        )
        if log.get("error_message"):
            st.caption(f"Error: {log['error_message']}")


def _render_macro_variable_inputs(macro_id: int, template_content: str) -> dict[str, str]:
    vars_found = extract_template_variables(template_content)
    var_values: dict[str, str] = {}
    if not vars_found:
        return var_values

    st.markdown("###### Template Variables")
    current_sid = st.session_state.get("session_id") or ""
    for var in vars_found:
        default_val = current_sid if var == "session_id" else ""
        val = st.text_input(
            f"{{{var}}}",
            value=default_val,
            key=f"macro_var_{macro_id}_{var}",
            placeholder=f"Value for {var}",
        )
        if val.strip():
            var_values[var] = val.strip()
    return var_values


def _render_macro_preview_and_apply(macro: dict, var_values: dict[str, str]):
    col_preview, col_apply = st.columns(2)
    if col_preview.button("Preview", key=f"preview_macro_{macro['id']}"):
        res = render_macro(macro["id"], variables=var_values, fallback_defaults=True)
        if res:
            st.session_state[f"macro_preview_{macro['id']}"] = res.get("rendered_content", "")

    preview_cached = st.session_state.get(f"macro_preview_{macro['id']}")
    if preview_cached:
        st.markdown("**Rendered Preview:**")
        st.info(preview_cached)

    if col_apply.button("Apply to Session", key=f"apply_macro_{macro['id']}"):
        current_sid = st.session_state.get("session_id")
        if not current_sid:
            st.error("No active chat session. Please start or load a session first.")
            return

        with st.spinner("Applying macro to session..."):
            res = apply_macro_to_session(
                session_id=current_sid,
                macro_id=macro["id"],
                variables=var_values,
                update_status=True,
                append_tags=True,
            )
            if res:
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append(
                    {"role": "user", "content": f"[Applied Macro: {macro['title']}]"}
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": res.get("rendered_content", "")}
                )
                st.session_state.sessions = list_sessions()
                st.success("Macro applied!")
                st.rerun()


def _render_macro_browser():
    st.markdown("##### Pre-approved Templates")
    categories = list_macro_categories()
    cat_filter_options = ["All Categories", *categories]
    selected_cat = st.selectbox(
        "Filter by category",
        options=cat_filter_options,
        key="macro_category_filter",
    )
    filter_arg = None if selected_cat == "All Categories" else selected_cat
    macros_list = list_macros(category=filter_arg)
    if not macros_list:
        st.caption("No macro templates found.")
        return

    macro_options = {f"{m['title']} ({m['shortcut']})": m for m in macros_list}
    chosen_label = st.selectbox(
        "Select macro",
        options=list(macro_options.keys()),
        key="selected_macro_choice",
    )
    chosen_macro = macro_options[chosen_label]

    status_str = (
        f" · 🎯 Sets status to `{chosen_macro['status_action']}`"
        if chosen_macro.get("status_action")
        else ""
    )
    st.caption(f"Category: **{chosen_macro['category']}**{status_str}")
    if chosen_macro.get("tags"):
        tag_pills = " ".join([f"`{t}`" for t in chosen_macro["tags"]])
        st.caption(f"Tags: {tag_pills}")

    var_values = _render_macro_variable_inputs(chosen_macro["id"], chosen_macro["content"])
    _render_macro_preview_and_apply(chosen_macro, var_values)

    if st.button("Delete Macro", key=f"del_macro_{chosen_macro['id']}") and delete_macro(
        chosen_macro["id"]
    ):
        st.success("Macro deleted.")
        st.rerun()


def _render_macro_creator():
    st.markdown("---")
    st.markdown("##### Create New Template")
    new_title = st.text_input(
        "Title", key="new_macro_title", placeholder="E.g., Move-in Instructions"
    )
    new_shortcut = st.text_input(
        "Shortcut", key="new_macro_shortcut", placeholder="E.g., /move-in"
    )
    new_cat = st.text_input("Category", key="new_macro_category", value="General")
    new_action = st.selectbox(
        "Status Action",
        options=["None", *SESSION_STATUS_OPTIONS],
        key="new_macro_status_action",
    )
    new_tags = st.text_input(
        "Tags (comma separated)",
        key="new_macro_tags",
        placeholder="e.g., leasing, onboarding",
    )
    new_content = st.text_area(
        "Content Template",
        key="new_macro_content",
        placeholder="Hello {customer_name}, welcome to unit {unit_id}!\nContact: {support_contact}",
    )

    if st.button("Save Template", key="save_new_macro"):
        if not new_title.strip() or not new_shortcut.strip() or not new_content.strip():
            st.error("Title, shortcut, and content are required.")
            return
        tags_list = [t.strip() for t in new_tags.split(",") if t.strip()]
        action_val = None if new_action == "None" else new_action
        created = create_macro(
            title=new_title.strip(),
            shortcut=new_shortcut.strip(),
            category=new_cat.strip() or "General",
            content=new_content.strip(),
            tags=tags_list,
            status_action=action_val,
        )
        if created:
            st.success(f"Macro '{created['title']}' created!")
            st.rerun()


def _render_smart_macro_suggestions():
    current_sid = st.session_state.get("session_id")
    if not current_sid:
        return

    res = get_session_macro_suggestions(current_sid, top_k=2, min_score=0.3)
    if not res or not res.get("suggestions"):
        return

    st.markdown("##### 💡 Smart Suggestions")
    detected_intent = res.get("detected_intent", "unknown")
    if detected_intent and detected_intent != "unknown":
        pretty_intent = detected_intent.replace("_", " ").title()
        st.caption(f"🎯 Detected Intent: **{pretty_intent}**")

    for sug in res.get("suggestions", []):
        score_pct = int(sug.get("score", 0.0) * 100)
        st.markdown(f"**{sug['title']}** (`{sug['shortcut']}`) — **{score_pct}% Match**")
        reasons = sug.get("match_reasons", [])
        if reasons:
            st.caption(" · ".join(reasons))

        if st.button("Apply Suggestion", key=f"apply_sug_{sug['macro_id']}"):
            with st.spinner("Applying suggestion..."):
                applied = apply_macro_to_session(
                    session_id=current_sid,
                    macro_id=sug["macro_id"],
                    variables=sug.get("suggested_variables", {}),
                    update_status=True,
                    append_tags=True,
                )
                if applied:
                    if "messages" not in st.session_state:
                        st.session_state["messages"] = []
                    st.session_state["messages"].append(
                        {"role": "user", "content": f"[Applied Suggestion: {sug['title']}]"}
                    )
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": applied.get("rendered_content", "")}
                    )
                    st.session_state["sessions"] = list_sessions()
                    st.success("Smart suggestion applied!")
                    st.rerun()

    st.markdown("---")


def _render_macro_query_tester():
    with st.expander("🔍 Test Query Intent & Matching"):
        test_query = st.text_input(
            "Test customer query",
            key="macro_tester_query",
            placeholder="e.g. pipe leaking in Apt 3B",
        )
        if test_query.strip():
            res = suggest_macros(test_query.strip(), top_k=3, min_score=0.2)
            if res:
                detected_intent = res.get("detected_intent", "unknown")
                intent_conf = res.get("intent_confidence", 0.0)
                conf_pct = int(intent_conf * 100)
                pretty_intent = detected_intent.replace("_", " ").title()
                st.caption(f"Intent: **{pretty_intent}** ({conf_pct}% confidence)")
                ext_vars = res.get("extracted_variables", {})
                if ext_vars:
                    vars_str = ", ".join([f"`{k}: {v}`" for k, v in ext_vars.items()])
                    st.caption(f"Entities: {vars_str}")

                suggestions = res.get("suggestions", [])
                if suggestions:
                    for s in suggestions:
                        match_pct = int(s["score"] * 100)
                        st.markdown(f"- **{s['title']}** (`{s['shortcut']}`) — {match_pct}%")
                else:
                    st.caption("No matching templates above threshold.")


def _render_quick_responses_panel():
    with st.sidebar.expander("Quick Responses & Macros"):
        _render_smart_macro_suggestions()
        _render_macro_browser()
        _render_macro_query_tester()
        _render_macro_creator()


def _render_webhook_manager():
    with st.sidebar.expander("Webhooks & Alerting"):
        _render_webhook_subscriptions()
        _render_webhook_register()
        _render_webhook_audit_log()


def _render_sla_compliance_metrics():
    analytics = get_sla_compliance_analytics()
    if analytics:
        st.markdown("#### SLA Performance")
        col1, col2 = st.columns(2)
        col1.metric("Compliance Rate", f"{analytics.get('compliance_rate', 100.0):.1f}%")
        col2.metric("Breached", analytics.get("breached_sessions", 0))

        m_col1, m_col2 = st.columns(2)
        m_col1.metric("Met", analytics.get("met_sessions", 0))
        m_col2.metric("Approaching", analytics.get("approaching_breach_sessions", 0))
    else:
        st.caption("No compliance analytics available yet.")


def _render_sla_alerts_trigger():
    if st.button("Evaluate Escalation Alerts", key="btn_eval_sla_alerts"):
        with st.spinner("Evaluating SLA escalation alerts..."):
            alert_res = evaluate_sla_alerts(approaching_threshold_minutes=30)
            if alert_res:
                n_alerts = alert_res.get("alerts_triggered", 0)
                if n_alerts > 0:
                    st.warning(
                        f"Triggered {n_alerts} escalation alerts across active sessions!"
                    )
                else:
                    st.success("All active sessions within SLA limits. Zero alerts triggered.")
            else:
                st.error("Failed to evaluate escalation alerts.")


def _render_sla_policy_list():
    st.markdown("#### Configured SLA Policies")
    policies = list_sla_policies()
    if not policies:
        st.caption("No SLA policies configured.")
        return

    for p in policies:
        p_id = p.get("id")
        p_name = p.get("name")
        p_prio = p.get("priority", "medium")
        p_cat = p.get("category", "general")
        p_resp = p.get("response_time_minutes", 60)
        p_resol = p.get("resolution_time_minutes", 480)
        st.caption(
            f"**#{p_id} {p_name}** ({p_prio.upper()} / {p_cat})\n"
            f"Response: {p_resp}m | Resolution: {p_resol}m"
        )
        if p_id is not None and st.button("Delete Policy", key=f"del_policy_{p_id}"):
            if delete_sla_policy(int(p_id)):
                st.success(f"Deleted policy #{p_id}")
                st.rerun()
            else:
                st.error(f"Failed to delete policy #{p_id}")


def _render_sla_policy_creator():
    st.markdown("#### Add SLA Policy")
    new_name = st.text_input("Policy Name", key="new_sla_name", placeholder="e.g. VIP Urgent")
    new_prio = st.selectbox(
        "Priority",
        options=SESSION_PRIORITY_OPTIONS,
        index=0,
        format_func=lambda p: PRIORITY_EMOJIS.get(p, p.title()),
        key="new_sla_prio",
    )
    new_cat = st.text_input("Category", value="general", key="new_sla_cat")
    new_resp_min = st.number_input(
        "Response Target (minutes)", min_value=1, value=30, key="new_sla_resp"
    )
    new_resol_min = st.number_input(
        "Resolution Target (minutes)", min_value=1, value=240, key="new_sla_resol"
    )

    if st.button("Create SLA Policy", key="btn_create_sla_policy"):
        if not new_name.strip():
            st.error("Policy name is required.")
        elif new_resol_min < new_resp_min:
            st.error("Resolution target must be >= response target.")
        else:
            created = create_sla_policy(
                name=new_name.strip(),
                priority=new_prio,
                category=new_cat.strip() or "general",
                response_time_minutes=int(new_resp_min),
                resolution_time_minutes=int(new_resol_min),
            )
            if created:
                st.success(f"Created policy '{new_name}'")
                st.rerun()
            else:
                st.error("Failed to create SLA policy.")


def _render_sla_manager():
    with st.sidebar.expander("SLA Policies & Compliance"):
        _render_sla_compliance_metrics()
        _render_sla_alerts_trigger()
        st.markdown("---")
        _render_sla_policy_list()
        st.markdown("---")
        _render_sla_policy_creator()


def _render_support_agents_and_workload():
    with st.sidebar.expander("👥 Support Agents & Workload"):
        st.markdown("#### Team Workload Analytics")
        workload = get_agent_workload_analytics()
        if workload:
            c1, c2, c3 = st.columns(3)
            c1.metric("Active Agents", workload.get("active_agents", 0))
            c2.metric("Assigned Sessions", workload.get("total_assigned_sessions", 0))
            c3.metric("Available Capacity", workload.get("total_available_capacity", 0))

            tier_counts = workload.get("tier_distribution", {})
            st.caption(
                f"**Tier Distribution:** T1: {tier_counts.get('tier_1', 0)} | "
                f"T2: {tier_counts.get('tier_2', 0)} | "
                f"T3: {tier_counts.get('tier_3', 0)}"
            )

        st.markdown("---")
        st.markdown("#### Agent Directory")
        agents = list_support_agents() or []
        if not agents:
            st.caption("No agents configured.")
        else:
            for ag in agents:
                status_dot = "🟢" if ag.get("is_active") else "⚪"
                tier_badge = ag.get("tier", "tier_1").upper()
                max_chats = ag.get("max_concurrent_chats", 5)
                st.markdown(
                    f"**{status_dot} {ag.get('name')}** (`{ag.get('agent_id')}`)\n"
                    f"- {tier_badge} | {ag.get('department')} | Max: {max_chats} chats"
                )
                toggle_btn_label = "Deactivate" if ag.get("is_active") else "Activate"
                agent_id_str = str(ag.get("agent_id") or "")
                if agent_id_str and st.button(
                    f"{toggle_btn_label} {ag.get('name')}",
                    key=f"btn_toggle_agent_{agent_id_str}",
                ):
                    new_active = not ag.get("is_active")
                    update_support_agent(agent_id_str, is_active=new_active)
                    st.rerun()

        st.markdown("---")
        st.markdown("#### Add Support Agent")
        new_ag_id = st.text_input("Agent ID", placeholder="agent_alex", key="new_agent_id")
        new_ag_name = st.text_input("Full Name", placeholder="Alex Smith", key="new_agent_name")
        new_ag_email = st.text_input("Email", placeholder="alex@example.com", key="new_agent_email")
        new_ag_tier = st.selectbox(
            "Agent Tier",
            options=AGENT_TIER_OPTIONS,
            format_func=lambda t: AGENT_TIER_LABELS.get(t, t),
            key="new_agent_tier",
        )
        new_ag_dept = st.text_input(
            "Department", value="Customer Care", key="new_agent_dept"
        )

        if st.button("Add Support Agent", key="btn_create_support_agent"):
            if not new_ag_id.strip() or not new_ag_name.strip() or not new_ag_email.strip():
                st.error("Agent ID, Name, and Email are required.")
            else:
                created = create_support_agent(
                    agent_id=new_ag_id.strip(),
                    name=new_ag_name.strip(),
                    email=new_ag_email.strip(),
                    tier=new_ag_tier,
                    department=new_ag_dept.strip() or "Customer Care",
                )
                if created:
                    st.success(f"Agent '{new_ag_name}' created successfully!")
                    st.rerun()
                else:
                    st.error("Failed to create agent. Check ID or connection.")


REVIEW_STATUS_OPTIONS = ["pending_review", "reviewed", "followup_required", "archived"]


def _render_csat_and_agent_scorecards():
    with st.sidebar.expander("⭐ CSAT Queue & Agent Scorecards"):
        st.markdown("#### Multi-Criteria CSAT Summary")
        csat_sum = get_csat_summary()
        if csat_sum:
            c1, c2, c3 = st.columns(3)
            c1.metric("Avg CSAT", f"{csat_sum.get('avg_csat_score', 0.0):.2f} ★")
            c2.metric("Pending Review", csat_sum.get("pending_review_count", 0))
            c3.metric("Follow-up", csat_sum.get("followup_required_count", 0))

            res_avg = csat_sum.get("avg_resolution_score")
            help_avg = csat_sum.get("avg_helpfulness_score")
            speed_avg = csat_sum.get("avg_speed_score")
            if res_avg is not None or help_avg is not None or speed_avg is not None:
                st.caption(
                    f"**Criteria:** Resolution: {res_avg or '-'} | "
                    f"Helpfulness: {help_avg or '-'} | Speed: {speed_avg or '-'}"
                )

        st.markdown("---")
        st.markdown("#### Agent Performance Scorecards")
        cards_resp = get_agent_scorecards() or {}
        scorecards = cards_resp.get("scorecards", [])
        if not scorecards:
            st.caption("No agent CSAT scorecards recorded yet.")
        else:
            for card in scorecards:
                ag_id = card.get("agent_id", "unassigned")
                tier = card.get("tier", "tier_1").upper()
                avg_score = card.get("avg_csat_score", 0.0)
                sat_rate = card.get("satisfaction_rate", 0.0)
                tot_ratings = card.get("total_ratings", 0)
                st.markdown(
                    f"**`{ag_id}`** ({tier}) — **{avg_score:.2f} ★** "
                    f"({sat_rate:.1f}% sat, {tot_ratings} ratings)"
                )

        st.markdown("---")
        st.markdown("#### Operator Feedback Review Queue")
        status_filter = st.selectbox(
            "Filter Queue Status",
            options=["All", *REVIEW_STATUS_OPTIONS],
            key="csat_queue_status_filter",
        )
        q_status = None if status_filter == "All" else status_filter
        queue_data = list_feedback_review_queue(review_status=q_status, limit=15) or {}
        q_items = queue_data.get("items", [])
        if not q_items:
            st.caption("No feedback items in queue matching filter.")
        else:
            for q_item in q_items:
                fid = q_item["id"]
                sid = q_item.get("session_id", "")[:8]
                score_val = q_item.get("score") or ("5" if q_item.get("rating") == 1 else "1")
                cur_rev_status = q_item.get("review_status", "pending_review")
                assigned = q_item.get("assigned_agent") or "unassigned"
                comment_val = q_item.get("comment") or "*(no comment)*"
                st.markdown(
                    f"**#{fid} · `{sid}` · {score_val}★** [{cur_rev_status}] "
                    f"(Agent: `{assigned}`)\n> {comment_val}"
                )
                new_rev_status = st.selectbox(
                    f"Update Status #{fid}",
                    options=REVIEW_STATUS_OPTIONS,
                    index=(
                        REVIEW_STATUS_OPTIONS.index(cur_rev_status)
                        if cur_rev_status in REVIEW_STATUS_OPTIONS
                        else 0
                    ),
                    key=f"rev_status_sel_{fid}",
                )
                rev_notes = st.text_input(
                    f"Reviewer Notes #{fid}",
                    value=q_item.get("reviewer_notes") or "",
                    key=f"rev_notes_in_{fid}",
                )
                if st.button(f"Save Review #{fid}", key=f"btn_save_rev_{fid}") and (
                    update_feedback_review(
                        fid,
                        review_status=new_rev_status,
                        reviewer_notes=rev_notes,
                    )
                ):
                    st.success(f"Feedback #{fid} review updated!")
                    st.rerun()


def _render_knowledge_studio_kpis(analytics):
    if not analytics:
        return
    col1, col2 = st.columns(2)
    col1.metric("Total Gaps", analytics.get("total_gaps", 0))
    col2.metric("Resolution Rate", f"{analytics.get('gap_resolution_rate', 0.0)}%")
    col3, col4 = st.columns(2)
    col3.metric("Published Articles", analytics.get("published_articles_count", 0))
    col4.metric("Est. Deflections", analytics.get("estimated_deflected_queries", 0))
    st.markdown("---")


def _render_knowledge_gaps_queue():
    st.markdown("#### 🚨 Knowledge Gaps Queue")
    gaps, _ = list_knowledge_gaps(limit=20)
    if not gaps:
        st.caption("No knowledge gaps logged.")
        return
    for gap in gaps:
        gid = gap["id"]
        st.markdown(
            f"**#{gid}: {gap['query']}**  \n"
            f"Category: `{gap.get('category')}` | Priority: `{gap.get('priority')}` | "
            f"Hits: `{gap.get('frequency', 1)}` | Status: `{gap.get('status')}`"
        )
        if gap.get("status") == "open" and st.button(
            f"Dismiss Gap #{gid}", key=f"btn_dismiss_gap_{gid}"
        ):
            update_knowledge_gap(gid, status="dismissed")
            st.rerun()
        st.markdown("---")


def _render_knowledge_articles_publisher():
    st.markdown("#### 📝 Knowledge Articles & Publisher")
    articles, _ = list_knowledge_articles(limit=20)
    if not articles:
        st.caption("No knowledge articles in studio.")
        return
    for art in articles:
        aid = art["id"]
        status_badge = "🟢 Published" if art.get("status") == "published" else "🟡 Draft"
        st.markdown(
            f"**#{aid}: {art['title']}** [{status_badge}]  \n"
            f"Category: `{art.get('category')}` | Author: `{art.get('author')}`"
        )
        if art.get("status") == "draft":
            target_col = st.text_input(
                f"Target Collection #{aid}",
                value="default",
                key=f"pub_col_{aid}",
            )
            if st.button(f"🚀 Publish to RAG #{aid}", key=f"btn_pub_art_{aid}"):
                with st.spinner("Publishing to vector knowledge base..."):
                    pub_res = publish_knowledge_article(aid, collection=target_col)
                    if pub_res:
                        st.success(f"Article #{aid} published to '{target_col}'!")
                        st.rerun()
        st.markdown("---")


def _render_knowledge_studio():
    with st.sidebar.expander("📚 Knowledge Gaps & Article Studio"):
        analytics = get_knowledge_analytics()
        _render_knowledge_studio_kpis(analytics)

        if st.button("🔍 Scan Sessions for Gaps", key="btn_scan_kb_gaps"):
            with st.spinner("Scanning support sessions..."):
                scan_res = scan_knowledge_gaps()
                if scan_res:
                    st.success(
                        f"Scan complete: {scan_res.get('total_gaps_identified', 0)} "
                        f"gaps found across {scan_res.get('scanned_sessions_count', 0)} sessions."
                    )
                    st.rerun()

        _render_knowledge_gaps_queue()
        _render_knowledge_articles_publisher()


def display_sidebar():
    _init_config()
    st.sidebar.caption(f"API: {API_BASE_URL}")
    _render_health_status()
    _render_reset_chat()
    _render_session_history()
    _render_model_selector()
    active_collection = _render_collection_picker()
    _render_collection_insights(active_collection)
    _render_batch_rechunk(active_collection)
    _render_upload_document(active_collection)
    _render_refresh_documents(active_collection)
    _render_document_inspector()
    _render_retrieval_filters()
    _render_document_list()
    _render_feedback_analytics()
    _render_feedback_review()
    _render_csat_and_agent_scorecards()
    _render_support_triage_analytics()
    _render_quick_responses_panel()
    _render_webhook_manager()
    _render_sla_manager()
    _render_support_agents_and_workload()
    _render_knowledge_studio()
    _render_ops_metrics()


