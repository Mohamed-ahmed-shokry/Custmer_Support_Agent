from typing import Any

import streamlit as st
from api.macros import extract_template_variables
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings

from app.api_utils import (
    API_BASE_URL,
    apply_macro_to_session,
    assign_session,
    auto_assign_session,
    complete_inspection,
    convert_inspection_item_to_work_order,
    create_billing_transaction,
    create_inspection,
    create_lease_renewal,
    create_macro,
    create_session_inspection,
    create_session_lease_renewal,
    create_sla_policy,
    create_support_agent,
    create_tenant,
    create_unit,
    create_webhook,
    create_work_order,
    create_work_order_from_session,
    delete_billing_transaction,
    delete_collection,
    delete_document,
    delete_documents,
    delete_inspection,
    delete_lease_renewal,
    delete_macro,
    delete_session,
    delete_sessions,
    delete_sla_policy,
    delete_tenant,
    delete_unit,
    delete_webhook,
    delete_work_order,
    draft_article_from_session,
    evaluate_sla_alerts,
    export_session,
    get_agent_scorecards,
    get_agent_workload_analytics,
    get_billing_metrics,
    get_business_hours_status,
    get_collection_analytics,
    get_collections_details,
    get_config,
    get_csat_summary,
    get_document_details,
    get_feedback_analytics,
    get_health,
    get_inspection_metrics,
    get_knowledge_analytics,
    get_lease_renewal_metrics,
    get_metrics,
    get_quota,
    get_session_assignment_history,
    get_session_history,
    get_session_macro_suggestions,
    get_session_sla_status,
    get_session_tenant_context,
    get_sla_compliance_analytics,
    get_stats,
    get_support_triage_analytics,
    get_tenant_inspections,
    get_tenant_lease_renewals,
    get_tenant_ledger,
    get_tenant_support_history,
    get_unit_work_orders,
    get_work_order_metrics,
    link_session_tenant,
    list_billing_transactions,
    list_collections,
    list_documents,
    list_feedback,
    list_feedback_review_queue,
    list_inspections,
    list_knowledge_articles,
    list_knowledge_gaps,
    list_lease_renewals,
    list_macro_categories,
    list_macros,
    list_sessions,
    list_sla_policies,
    list_support_agents,
    list_tenants,
    list_units,
    list_webhook_deliveries,
    list_webhooks,
    list_work_orders,
    ping_webhook,
    publish_inspection_document,
    publish_knowledge_article,
    publish_lease_renewal_document,
    rechunk_collection,
    rechunk_document,
    record_session_payment,
    record_tenant_payment,
    rename_collection,
    rename_session,
    render_macro,
    scan_knowledge_gaps,
    search_sessions,
    sign_lease_renewal,
    suggest_macros,
    summarize_session,
    update_billing_transaction,
    update_feedback_review,
    update_inspection,
    update_knowledge_gap,
    update_session,
    update_support_agent,
    update_webhook,
    update_work_order,
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
    _render_session_tenant_card(selected)


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


def _render_session_work_order_dispatch(selected: str):
    with st.sidebar.expander("🛠️ Dispatch Work Order"):
        wo_title = st.text_input(
            "Issue Title",
            key=f"wo_title_{selected}",
            placeholder="e.g. Leaking kitchen faucet",
        )
        wo_desc = st.text_area(
            "Issue Description",
            key=f"wo_desc_{selected}",
            placeholder="Describe problem details, symptoms, and urgency",
        )
        c_cat, c_prio = st.columns(2)
        wo_cat = c_cat.selectbox(
            "Category",
            [
                "plumbing",
                "electrical",
                "hvac",
                "appliance",
                "pest_control",
                "structural",
                "general",
            ],
            key=f"wo_cat_{selected}",
        )
        wo_prio = c_prio.selectbox(
            "Priority",
            ["low", "medium", "high", "emergency"],
            index=1,
            key=f"wo_prio_{selected}",
        )
        wo_perm = st.selectbox(
            "Entry Permission",
            ["permission_granted", "call_first", "resident_must_be_present"],
            key=f"wo_perm_{selected}",
        )
        wo_est = st.number_input(
            "Est. Cost ($)",
            min_value=0.0,
            step=25.0,
            value=0.0,
            key=f"wo_est_{selected}",
        )

        if st.button("🚀 Create Work Order", key=f"btn_create_wo_{selected}"):
            if not wo_title.strip() or not wo_desc.strip():
                st.error("Title and description are required.")
            else:
                wo_payload = {
                    "title": wo_title.strip(),
                    "description": wo_desc.strip(),
                    "category": wo_cat,
                    "priority": wo_prio,
                    "entry_permission": wo_perm,
                    "estimated_cost": float(wo_est) if wo_est > 0 else None,
                }
                res = create_work_order_from_session(selected, wo_payload)
                if res:
                    st.success(
                        f"Work order created! ID: {res.get('work_order', {}).get('id', '')}"
                    )
                    st.rerun()
                else:
                    st.error("Failed to create work order.")


def _render_session_billing_widget(selected: str, tenant: dict):
    tenant_id = tenant.get("id")
    if not tenant_id:
        return

    ledger = get_tenant_ledger(tenant_id)
    if ledger:
        cur_bal = ledger.get("current_balance", 0.0)
        overdue_amt = ledger.get("overdue_amount", 0.0)
        overdue_cnt = ledger.get("overdue_count", 0)
        last_pay = ledger.get("last_payment")

        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💰 Resident Financial Ledger")
        bc1, bc2 = st.sidebar.columns(2)
        bc1.metric("Balance Due", f"${cur_bal:,.2f}")
        bc2.metric("Overdue", f"${overdue_amt:,.2f}")

        if overdue_cnt > 0:
            st.sidebar.error(f"🚨 {overdue_cnt} Overdue Charge(s) (${overdue_amt:,.2f})")
        else:
            st.sidebar.success("✅ Account Current / Paid Up")

        if last_pay:
            last_date = (last_pay.get("paid_at") or "")[:10]
            st.sidebar.caption(
                f"**Last Payment:** ${last_pay.get('amount', 0):,.2f} on {last_date} "
                f"({last_pay.get('payment_method', 'portal')})"
            )

    with st.sidebar.expander("💳 Record Resident Payment"):
        default_pay = float(tenant.get("balance_due", 0.0))
        if default_pay <= 0.0:
            default_pay = float(tenant.get("monthly_rent", 1000.0))

        pay_amount = st.number_input(
            "Payment Amount ($)",
            min_value=1.0,
            value=default_pay,
            step=50.0,
            key=f"pay_amt_{selected}",
        )
        pay_method = st.selectbox(
            "Method",
            ["online_portal", "ach", "credit_card", "debit_card", "check", "cashier_check"],
            key=f"pay_meth_{selected}",
        )
        pay_ref = st.text_input(
            "Reference # (Auth/Check #)",
            placeholder="e.g. AUTH-88231",
            key=f"pay_ref_{selected}",
        )
        pay_desc = st.text_input(
            "Payment Memo",
            value="Resident Rent Payment",
            key=f"pay_desc_{selected}",
        )

        if st.button("💵 Submit Payment", key=f"btn_pay_{selected}"):
            with st.spinner("Processing resident payment..."):
                pay_payload = {
                    "amount": float(pay_amount),
                    "payment_method": pay_method,
                    "reference_number": pay_ref.strip(),
                    "description": pay_desc.strip(),
                }
                res = record_session_payment(selected, pay_payload)
                if res:
                    new_bal_val = res.get("new_balance", 0.0)
                    st.success(
                        f"Payment of ${pay_amount:,.2f} recorded! New balance: ${new_bal_val:,.2f}"
                    )
                    st.rerun()
                else:
                    st.error("Failed to record payment.")


def _render_session_lease_renewal_widget(selected: str, tenant: dict):  # noqa: PLR0915
    tenant_id = tenant.get("id")
    if not tenant_id:
        return

    renewals_resp = get_tenant_lease_renewals(tenant_id)
    renewals = renewals_resp.get("items", []) if renewals_resp else []
    active_renewals = [
        r for r in renewals if r.get("status") in ("draft", "offered", "accepted")
    ]

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📝 Lease Renewal & Agreements")

    if active_renewals:
        for lr in active_renewals:
            status_val = lr.get("status", "")
            status_badge = "📄 Offered" if status_val == "offered" else f"📌 {status_val.title()}"
            prop_rent = lr.get("proposed_rent", 0.0)
            diff_rent = prop_rent - lr.get("current_rent", 0.0)
            sign_str = f"+${diff_rent:,.2f}" if diff_rent >= 0 else f"-${abs(diff_rent):,.2f}"

            st.sidebar.info(
                f"**Active Offer ({lr.get('id')}):** {status_badge}\n\n"
                f"- **New Rent:** ${prop_rent:,.2f}/mo ({sign_str})\n"
                f"- **Term:** {lr.get('term_months', 12)} mos "
                f"({lr.get('start_date', '')} to {lr.get('end_date', '')})\n"
                f"- **Expires:** {lr.get('expires_at', '')[:10]}"
            )

            if status_val in ("offered", "accepted"):
                with st.sidebar.expander(f"✍️ E-Sign Offer {lr.get('id')}"):
                    t_full_name = (
                        f"{tenant.get('first_name', '')} {tenant.get('last_name', '')}".strip()
                    )
                    sig_name = st.text_input(
                        "Resident Signature Name",
                        value=t_full_name,
                        key=f"lr_sign_name_{selected}_{lr.get('id')}",
                    )
                    sig_notes = st.text_input(
                        "Signature Audit Notes",
                        value="Signed during active concierge support session",
                        key=f"lr_sign_notes_{selected}_{lr.get('id')}",
                    )
                    if st.button(
                        "Confirm Digital E-Signature",
                        key=f"btn_sign_lr_{selected}_{lr.get('id')}",
                    ):
                        if not sig_name.strip():
                            st.error("Signature name is required to execute agreement.")
                        else:
                            with st.spinner("Executing digital signature..."):
                                sign_res = sign_lease_renewal(
                                    lr["id"],
                                    {
                                        "signature_name": sig_name.strip(),
                                        "signature_ip": "127.0.0.1",
                                        "notes": sig_notes.strip(),
                                    },
                                )
                                if sign_res:
                                    st.success("Lease renewal digitally executed!")
                                    st.rerun()
                                else:
                                    st.error("Failed to sign renewal offer.")

    with st.sidebar.expander("📄 Generate 1-Click Renewal Offer"):
        curr_rent = float(tenant.get("monthly_rent", 1000.0))
        calc_default_prop = round(curr_rent * 1.05, 2)
        prop_rent_in = st.number_input(
            "Proposed Monthly Rent ($)",
            min_value=1.0,
            value=calc_default_prop,
            step=25.0,
            key=f"sess_prop_rent_{selected}",
        )
        term_in = st.selectbox(
            "Renewal Term",
            [6, 12, 18, 24],
            index=1,
            format_func=lambda x: f"{x} Months",
            key=f"sess_term_{selected}",
        )
        c_conc, c_dep = st.columns(2)
        conc_amt = c_conc.number_input(
            "Concession ($)",
            min_value=0.0,
            value=0.0,
            step=50.0,
            key=f"sess_conc_amt_{selected}",
        )
        dep_chg = c_dep.number_input(
            "Sec. Dep. Change ($)",
            value=0.0,
            step=50.0,
            key=f"sess_dep_chg_{selected}",
        )
        conc_notes_in = st.text_input(
            "Concession Notes",
            placeholder="e.g. First month $100 off incentive",
            key=f"sess_conc_notes_{selected}",
        )
        offer_notes_in = st.text_area(
            "Offer Notes",
            value="Standard renewal offer generated during support session",
            key=f"sess_offer_notes_{selected}",
        )

        if st.button("🚀 Create Renewal Offer", key=f"btn_create_lr_{selected}"):
            with st.spinner("Creating renewal offer..."):
                payload = {
                    "tenant_id": tenant_id,
                    "unit_id": tenant.get("unit_id"),
                    "proposed_rent": float(prop_rent_in),
                    "current_rent": curr_rent,
                    "term_months": int(term_in),
                    "concession_amount": float(conc_amt),
                    "concession_notes": conc_notes_in.strip(),
                    "security_deposit_change": float(dep_chg),
                    "notes": offer_notes_in.strip(),
                    "status": "offered",
                }
                res = create_session_lease_renewal(selected, payload)
                if res:
                    new_id = res.get("renewal", {}).get("id", "")
                    st.success(f"Renewal offer created! ID: {new_id}")
                    st.rerun()
                else:
                    st.error("Failed to create renewal offer.")


def _render_session_inspection_widget(selected: str, tenant: dict):
    tenant_id = tenant.get("id")
    if not tenant_id:
        return

    inspections_resp = get_tenant_inspections(tenant_id)
    inspections = inspections_resp.get("items", []) if inspections_resp else []
    active_insps = [
        insp for insp in inspections if insp.get("status") in ("scheduled", "in_progress")
    ]

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Move-In/Out Inspections")

    if active_insps:
        for insp in active_insps:
            insp_id = insp.get("inspection_id", "")
            itype = insp.get("inspection_type", "move_out").replace("_", " ").title()
            istatus = insp.get("status", "scheduled")
            badge = "🔍 In Progress" if istatus == "in_progress" else "📅 Scheduled"
            date_str = insp.get("scheduled_date") or "Pending"
            ded_est = insp.get("total_estimated_deductions", 0.0)

            st.sidebar.info(
                f"**{badge} ({insp_id}):** {itype}\n\n"
                f"- **Scheduled:** {date_str}\n"
                f"- **Inspector:** {insp.get('inspector_name') or 'Unassigned'}\n"
                f"- **Est. Deductions:** ${ded_est:,.2f}"
            )

    with st.sidebar.expander("📋 Schedule Move-In/Out Inspection"):
        insp_type_sel = st.selectbox(
            "Inspection Type",
            ["move_in", "move_out", "pre_move_out", "annual", "turnover_punchlist"],
            format_func=lambda x: x.replace("_", " ").title(),
            key=f"sess_insp_type_{selected}",
        )
        insp_date_in = st.text_input(
            "Scheduled Date (YYYY-MM-DD)",
            value="2026-10-25",
            key=f"sess_insp_date_{selected}",
        )
        inspector_in = st.text_input(
            "Inspector Name",
            value="Property Operations Specialist",
            key=f"sess_insp_agent_{selected}",
        )
        notes_in = st.text_area(
            "Inspection Notes",
            value="Scheduled during resident support session",
            key=f"sess_insp_notes_{selected}",
        )

        if st.button("🚀 Schedule Inspection", key=f"btn_create_insp_{selected}"):
            with st.spinner("Scheduling inspection..."):
                insp_payload = {
                    "unit_id": tenant.get("unit_id"),
                    "inspection_type": insp_type_sel,
                    "scheduled_date": insp_date_in.strip() if insp_date_in.strip() else None,
                    "inspector_name": inspector_in.strip() if inspector_in.strip() else None,
                    "notes": notes_in.strip(),
                    "status": "scheduled",
                }
                res = create_session_inspection(selected, insp_payload)
                if res:
                    new_insp_id = res.get("inspection", {}).get("inspection_id", "")
                    st.success(f"Inspection scheduled! ID: {new_insp_id}")
                    st.rerun()
                else:
                    st.error("Failed to schedule inspection.")


def _render_linked_tenant_details(selected, tenant, unit):
    t_name = f"{tenant.get('first_name', '')} {tenant.get('last_name', '')}".strip()
    st.sidebar.markdown(f"**Resident:** {t_name}")
    st.sidebar.caption(
        f"📧 {tenant.get('email', 'N/A')} | 📞 {tenant.get('phone', 'N/A')}"
    )
    if unit:
        u_info = f"Unit {unit.get('unit_number')} - {unit.get('property_name')}"
        st.sidebar.markdown(f"**Unit:** {u_info}")
        if unit.get("parking_spot"):
            st.sidebar.caption(f"🅿️ Spot: {unit['parking_spot']}")
        gate = unit.get("gate_code") or unit.get("access_code")
        if gate:
            st.sidebar.caption(f"🔑 Gate: {gate}")

    status = tenant.get("status") or "active"
    badge = "🟢" if status == "active" else "🔴"
    start_date = tenant.get("lease_start")
    end_date = tenant.get("lease_end")
    st.sidebar.markdown(f"**Lease:** {start_date} to {end_date} ({badge} {status})")
    rent_val = tenant.get("monthly_rent", 0.0)
    bal_val = tenant.get("balance_due", 0.0)
    bal_warn = " ⚠️" if bal_val > 0 else ""
    st.sidebar.caption(f"Rent: ${rent_val:,.2f}/mo | Balance: ${bal_val:,.2f}{bal_warn}")

    if unit and unit.get("id"):
        unit_wos = get_unit_work_orders(unit["id"], open_only=True)
        open_count = len(unit_wos.get("items", [])) if unit_wos else 0
        if open_count > 0:
            st.sidebar.warning(f"⚠️ {open_count} Open Work Order(s) for Unit")

    _render_session_billing_widget(selected, tenant)
    _render_session_lease_renewal_widget(selected, tenant)
    _render_session_inspection_widget(selected, tenant)
    _render_session_work_order_dispatch(selected)

    if st.sidebar.button("Unlink Resident", key=f"btn_unlink_tenant_{selected}"):
        with st.spinner("Unlinking tenant..."):
            res = link_session_tenant(selected, tenant_id=None, unit_id=None)
            if res:
                st.sidebar.success("Resident unlinked.")
                st.rerun()
            else:
                st.sidebar.error("Failed to unlink resident.")


def _render_link_tenant_selector(selected):
    st.sidebar.caption("No resident profile linked to this session.")
    all_tenants_resp = list_tenants(limit=100)
    tenants_list = all_tenants_resp.get("items", []) if all_tenants_resp else []
    if not tenants_list:
        return

    tenant_opts = ["(Select Tenant)"] + [t["id"] for t in tenants_list]
    tenant_names = {
        t["id"]: f"{t['first_name']} {t['last_name']} (Unit: {t.get('unit_id', 'None')})"
        for t in tenants_list
    }
    tenant_names["(Select Tenant)"] = "-- Select a resident to link --"
    chosen_tenant = st.sidebar.selectbox(
        "Link Resident",
        options=tenant_opts,
        format_func=lambda x: tenant_names.get(x, x),
        key=f"select_link_tenant_{selected}",
    )
    if st.sidebar.button("🔗 Link to Session", key=f"btn_link_tenant_{selected}"):
        if chosen_tenant != "(Select Tenant)":
            with st.spinner("Linking resident..."):
                res = link_session_tenant(selected, tenant_id=chosen_tenant)
                if res:
                    st.sidebar.success("Resident linked to session!")
                    st.rerun()
                else:
                    st.sidebar.error("Failed to link resident.")
        else:
            st.sidebar.warning("Please choose a resident to link.")


def _render_session_tenant_card(selected):
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🏢 Resident Context & Lease")
    ctx = get_session_tenant_context(selected)
    tenant = ctx.get("tenant") if ctx else None
    unit = ctx.get("unit") if ctx else None

    if tenant:
        _render_linked_tenant_details(selected, tenant, unit)
    else:
        _render_link_tenant_selector(selected)


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


def _render_tenants_tab():
    t_search = st.text_input(
        "Search Tenants", key="t_search_input", placeholder="Name, email, phone"
    )
    t_status = st.selectbox(
        "Status",
        ["All", "active", "past_due", "evicted", "former"],
        key="t_status_select",
    )
    status_filter = None if t_status == "All" else t_status
    tenants_resp = list_tenants(search=t_search, status=status_filter, limit=50)
    tenants = tenants_resp.get("items", []) if tenants_resp else []
    total = tenants_resp.get("total", 0) if tenants_resp else 0
    st.caption(f"Showing {len(tenants)} of {total} tenant(s)")

    for t in tenants[:10]:
        t_id = t["id"]
        full_name = f"{t['first_name']} {t['last_name']}"
        with st.expander(f"👤 {full_name} ({t.get('unit_id', 'No Unit')})"):
            st.caption(f"ID: `{t_id}` | Status: `{t.get('status')}`")
            st.caption(f"📧 {t.get('email')} | 📞 {t.get('phone')}")
            st.caption(f"Lease: {t.get('lease_start')} - {t.get('lease_end')}")
            rent_amount = t.get("monthly_rent", 0)
            bal_amount = t.get("balance_due", 0)
            st.caption(f"Rent: ${rent_amount:,.2f} | Balance: ${bal_amount:,.2f}")
            if st.button("Delete Tenant", key=f"btn_del_tenant_{t_id}") and delete_tenant(t_id):
                st.success(f"Deleted tenant {t_id}")
                st.rerun()

    with st.expander("➕ Register New Tenant"):
        new_id = st.text_input("Tenant ID", key="new_t_id", placeholder="e.g. tenant_401")
        col_n1, col_n2 = st.columns(2)
        new_first = col_n1.text_input("First Name", key="new_t_first")
        new_last = col_n2.text_input("Last Name", key="new_t_last")
        col_c1, col_c2 = st.columns(2)
        new_email = col_c1.text_input("Email", key="new_t_email")
        new_phone = col_c2.text_input("Phone", key="new_t_phone")
        new_unit = st.text_input("Unit ID", key="new_t_unit", placeholder="e.g. unit_101")
        col_l1, col_l2 = st.columns(2)
        new_start = col_l1.text_input("Lease Start", value="2026-01-01", key="new_t_start")
        new_end = col_l2.text_input("Lease End", value="2026-12-31", key="new_t_end")
        col_f1, col_f2 = st.columns(2)
        new_rent = col_f1.number_input(
            "Monthly Rent", min_value=0.0, value=1500.0, step=50.0, key="new_t_rent"
        )
        new_bal = col_f2.number_input("Balance Due", value=0.0, step=50.0, key="new_t_bal")
        if st.button("Save Tenant", key="btn_save_tenant"):
            if new_id and new_first and new_last and new_email and new_phone:
                payload = {
                    "id": new_id,
                    "first_name": new_first,
                    "last_name": new_last,
                    "email": new_email,
                    "phone": new_phone,
                    "unit_id": new_unit.strip() if new_unit.strip() else None,
                    "lease_start": new_start,
                    "lease_end": new_end,
                    "monthly_rent": float(new_rent),
                    "balance_due": float(new_bal),
                    "status": "active",
                }
                res = create_tenant(payload)
                if res:
                    st.success(f"Tenant {new_id} registered!")
                    st.rerun()
            else:
                st.warning("Please fill in all required tenant fields.")


def _render_units_tab():
    u_search = st.text_input(
        "Search Units", key="u_search_input", placeholder="Unit #, building, property"
    )
    units_resp = list_units(search=u_search, limit=50)
    units = units_resp.get("items", []) if units_resp else []
    total = units_resp.get("total", 0) if units_resp else 0
    st.caption(f"Showing {len(units)} of {total} unit(s)")

    for u in units[:10]:
        u_id = u["id"]
        with st.expander(f"🚪 Unit {u.get('unit_number')} ({u.get('property_name')})"):
            bldg_name = u.get("building_name", "N/A")
            floor_val = u.get("floor", 1)
            st.caption(f"ID: `{u_id}` | Bldg: {bldg_name} | Floor: {floor_val}")
            u_addr_full = (
                f"{u.get('address')}, {u.get('city')}, {u.get('state')} {u.get('zip_code')}"
            )
            st.caption(f"Address: {u_addr_full}")
            u_rent_amount = u.get("monthly_rent", 0)
            u_spot = u.get("parking_spot", "N/A")
            st.caption(f"Rent: ${u_rent_amount:,.2f} | Parking: {u_spot}")
            if st.button("Delete Unit", key=f"btn_del_unit_{u_id}") and delete_unit(u_id):
                st.success(f"Deleted unit {u_id}")
                st.rerun()

    with st.expander("➕ Add Property Unit"):
        unit_id = st.text_input("Unit ID", key="new_u_id", placeholder="e.g. unit_501")
        col_p1, col_p2 = st.columns(2)
        prop_name = col_p1.text_input("Property Name", value="Sunset Heights", key="new_u_prop")
        unit_num = col_p2.text_input("Unit Number", placeholder="501", key="new_u_num")
        u_addr = st.text_input("Street Address", value="100 Main St", key="new_u_addr")
        col_c1, col_c2, col_c3 = st.columns(3)
        u_city = col_c1.text_input("City", value="Austin", key="new_u_city")
        u_state = col_c2.text_input("State", value="TX", key="new_u_state")
        u_zip = col_c3.text_input("Zip Code", value="78701", key="new_u_zip")
        col_b1, col_b2 = st.columns(2)
        bldg = col_b1.text_input("Building", key="new_u_bldg")
        floor_num = col_b2.number_input("Floor", min_value=1, value=1, step=1, key="new_u_floor")
        u_rent = st.number_input(
            "Monthly Rent", min_value=0.0, value=1800.0, step=50.0, key="new_u_rent"
        )
        if st.button("Save Unit", key="btn_save_unit"):
            if unit_id and prop_name and unit_num and u_addr and u_city and u_state and u_zip:
                payload = {
                    "id": unit_id,
                    "property_name": prop_name,
                    "unit_number": unit_num,
                    "address": u_addr,
                    "city": u_city,
                    "state": u_state,
                    "zip_code": u_zip,
                    "building_name": bldg,
                    "floor": int(floor_num),
                    "monthly_rent": float(u_rent),
                }
                res = create_unit(payload)
                if res:
                    st.success(f"Unit {unit_id} created!")
                    st.rerun()
            else:
                st.warning("Please fill in required unit fields.")


def _render_tenant_history_tab():
    tenants_resp = list_tenants(limit=100)
    tenants = tenants_resp.get("items", []) if tenants_resp else []
    if not tenants:
        st.caption("No tenants found.")
        return
    tenant_choices = [t["id"] for t in tenants]
    tenant_map = {t["id"]: f"{t['first_name']} {t['last_name']} ({t['id']})" for t in tenants}
    selected_t = st.selectbox(
        "Select Tenant",
        options=tenant_choices,
        format_func=lambda tid: tenant_map.get(tid, tid),
        key="hist_tenant_select",
    )
    if st.button("Fetch Support History", key="btn_fetch_t_history"):
        hist = get_tenant_support_history(selected_t)
        if hist:
            total_sess = hist.get("total_sessions", 0)
            st.markdown(f"**Total Linked Sessions:** `{total_sess}`")
            for s in hist.get("sessions", []):
                sid = s.get("session_id", "")
                st.markdown(f"**Session `{sid[:8]}`** - Status: `{s.get('status')}`")
                if s.get("summary"):
                    st.caption(f"Summary: {s['summary']}")
                if s.get("rating"):
                    st.caption(f"Rating: {'⭐' * s['rating']}")
                st.markdown("---")
        else:
            st.info("No support history found for this tenant.")


def _render_tenant_and_property_directory():
    with st.sidebar.expander("🏢 Tenant & Property Directory"):
        tab = st.radio(
            "Directory Section",
            ["Tenants", "Units", "Support History"],
            horizontal=True,
            key="tenant_dir_tab_radio",
        )
        if tab == "Tenants":
            _render_tenants_tab()
        elif tab == "Units":
            _render_units_tab()
        else:
            _render_tenant_history_tab()


def _render_work_orders_board_tab():
    f_col1, f_col2 = st.columns(2)
    s_filter = f_col1.selectbox(
        "Status",
        ["All", "submitted", "scheduled", "in_progress", "completed", "cancelled"],
        key="wo_filter_status",
    )
    p_filter = f_col2.selectbox(
        "Priority",
        ["All", "low", "medium", "high", "emergency"],
        key="wo_filter_prio",
    )
    search_query = st.text_input("Search issues...", key="wo_search_input")

    wos_resp = list_work_orders(
        status=None if s_filter == "All" else s_filter,
        priority=None if p_filter == "All" else p_filter,
        search=search_query.strip() or None,
        limit=30,
    )
    items = wos_resp.get("items", []) if wos_resp else []
    total_items = wos_resp.get("total", 0) if wos_resp else 0
    st.caption(f"Showing {len(items)} of {total_items} work order(s)")

    if not items:
        st.info("No work orders found matching the filter.")

    for wo in items:
        wo_id = wo["id"]
        prio_badge = (
            "🚨"
            if wo["priority"] == "emergency"
            else "⚡"
            if wo["priority"] == "high"
            else "🔧"
        )
        st.markdown(f"**{prio_badge} {wo['title']}** (`{wo_id}`)")
        st.caption(
            f"Unit: {wo['unit_id']} | Status: {wo['status']} | "
            f"Cat: {wo['category']} | Prio: {wo['priority']}"
        )
        if wo.get("description"):
            st.text(wo["description"][:120])

        b_col1, b_col2, b_col3 = st.columns(3)
        if wo["status"] not in ("in_progress", "completed") and b_col1.button(
            "▶️ Start", key=f"btn_start_wo_{wo_id}"
        ):
            update_work_order(wo_id, {"status": "in_progress"})
            st.rerun()
        if wo["status"] != "completed" and b_col2.button(
            "✅ Done", key=f"btn_done_wo_{wo_id}"
        ):
            update_work_order(wo_id, {"status": "completed"})
            st.rerun()
        if b_col3.button("🗑️ Del", key=f"btn_del_wo_{wo_id}") and delete_work_order(
            wo_id
        ):
            st.success(f"Deleted {wo_id}")
            st.rerun()
        st.markdown("---")


def _render_create_work_order_tab():
    st.markdown("##### ➕ Create New Service Request")
    all_units = list_units(limit=100)
    unit_list = all_units.get("items", []) if all_units else []
    unit_opts = [u["id"] for u in unit_list] if unit_list else ["unit_101"]

    new_unit = st.selectbox("Property Unit", options=unit_opts, key="new_wo_unit")
    new_title = st.text_input(
        "Title", key="new_wo_title", placeholder="e.g. AC unit buzzing"
    )
    new_desc = st.text_area("Description", key="new_wo_desc")
    new_cat = st.selectbox(
        "Category",
        [
            "plumbing",
            "electrical",
            "hvac",
            "appliance",
            "pest_control",
            "structural",
            "general",
        ],
        key="new_wo_cat",
    )
    new_prio = st.selectbox(
        "Priority",
        ["low", "medium", "high", "emergency"],
        index=1,
        key="new_wo_prio",
    )
    new_perm = st.selectbox(
        "Permission to Enter",
        ["permission_granted", "call_first", "resident_must_be_present"],
        key="new_wo_perm",
    )
    new_assigned = st.text_input(
        "Assigned Staff", key="new_wo_assigned", placeholder="e.g. Bob HVAC"
    )
    new_est = st.number_input(
        "Estimated Cost ($)",
        min_value=0.0,
        step=25.0,
        value=0.0,
        key="new_wo_est",
    )

    if st.button("Save Work Order", key="btn_save_new_wo"):
        if not new_title.strip() or not new_desc.strip():
            st.warning("Please fill in title and description.")
        else:
            payload = {
                "unit_id": new_unit,
                "title": new_title.strip(),
                "description": new_desc.strip(),
                "category": new_cat,
                "priority": new_prio,
                "entry_permission": new_perm,
                "assigned_to": new_assigned.strip(),
                "estimated_cost": float(new_est) if new_est > 0 else None,
            }
            res = create_work_order(payload)
            if res:
                st.success(
                    f"Work order created with ID: {res.get('work_order', {}).get('id', '')}"
                )
                st.rerun()
            else:
                st.error("Failed to create work order.")


def _render_work_order_metrics_tab(metrics: dict):
    st.markdown("##### 📊 Maintenance Costs & Metrics")
    est_total = metrics.get("total_estimated_cost", 0.0)
    act_total = metrics.get("total_actual_cost", 0.0)
    mc1, mc2 = st.columns(2)
    mc1.metric("Est. Total Cost", f"${est_total:,.2f}")
    mc2.metric("Actual Total Cost", f"${act_total:,.2f}")

    st.markdown("**Status Breakdown:**")
    for st_name, count in (metrics.get("by_status") or {}).items():
        st.caption(f"- **{st_name}**: {count}")

    st.markdown("**Priority Breakdown:**")
    for pr_name, count in (metrics.get("by_priority") or {}).items():
        st.caption(f"- **{pr_name}**: {count}")


def _render_maintenance_board():
    with st.sidebar.expander("🛠️ Maintenance & Work Orders"):
        metrics = get_work_order_metrics() or {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", metrics.get("total_work_orders", 0))
        c2.metric("Open", metrics.get("open_work_orders", 0))
        c3.metric("In Progress", metrics.get("in_progress_work_orders", 0))
        c4.metric("Emergency", metrics.get("emergency_work_orders", 0))

        sub_tab = st.radio(
            "Board View",
            ["Work Orders", "Create Order", "Metrics & Costs"],
            horizontal=True,
            key="wo_board_tab_radio",
        )

        if sub_tab == "Work Orders":
            _render_work_orders_board_tab()
        elif sub_tab == "Create Order":
            _render_create_work_order_tab()
        else:
            _render_work_order_metrics_tab(metrics)


def _render_billing_board():
    with st.sidebar.expander("💰 Billing & Rent Ledgers"):
        metrics = get_billing_metrics() or {}
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.metric("Billed", f"${metrics.get('total_billed', 0.0):,.0f}")
        bc2.metric("Collected", f"${metrics.get('total_collected', 0.0):,.0f}")
        bc3.metric("Outstanding", f"${metrics.get('total_outstanding', 0.0):,.0f}")
        bc4.metric("Rate", f"{metrics.get('collection_rate', 0.0):.1f}%")

        b_tab = st.radio(
            "Billing Section",
            ["Transactions", "Record Payment", "Post Charge", "Financial KPIs"],
            horizontal=True,
            key="billing_board_tab_radio",
        )

        if b_tab == "Transactions":
            _render_billing_transactions_tab()
        elif b_tab == "Record Payment":
            _render_record_payment_tab()
        elif b_tab == "Post Charge":
            _render_post_charge_tab()
        else:
            _render_billing_metrics_tab(metrics)


def _render_billing_transactions_tab():
    c_f1, c_f2 = st.columns(2)
    stat_filter = c_f1.selectbox(
        "Status Filter",
        ["All", "posted", "pending", "paid", "overdue", "waived", "refunded"],
        key="tx_filter_status",
    )
    type_filter = c_f2.selectbox(
        "Type Filter",
        [
            "All",
            "rent",
            "security_deposit",
            "late_fee",
            "utility",
            "parking_fee",
            "pet_rent",
            "maintenance_charge",
            "payment",
            "credit_refund",
        ],
        key="tx_filter_type",
    )
    s_filter_val = None if stat_filter == "All" else stat_filter
    t_filter_val = None if type_filter == "All" else type_filter

    tx_resp = list_billing_transactions(
        status=s_filter_val, transaction_type=t_filter_val, limit=25
    )
    items = tx_resp.get("items", []) if tx_resp else []
    total = tx_resp.get("total", 0) if tx_resp else 0
    st.caption(f"Showing {len(items)} of {total} transaction(s)")

    for tx in items:
        tx_id = tx["id"]
        status_emoji = (
            "🟢"
            if tx.get("status") == "paid"
            else ("🔴" if tx.get("status") == "overdue" else "🟡")
        )
        t_type = tx.get("transaction_type", "charge").upper()
        amt = tx.get("amount", 0.0)
        due = tx.get("due_date") or "N/A"

        with st.expander(f"{status_emoji} #{tx_id}: {t_type} - ${amt:,.2f} ({tx.get('status')})"):
            st.caption(f"**Description:** {tx.get('description')}")
            st.caption(f"**Tenant:** `{tx.get('tenant_id')}` | **Unit:** `{tx.get('unit_id')}`")
            st.caption(f"**Due Date:** {due}")
            if tx.get("paid_at"):
                paid_str = tx["paid_at"][:19].replace("T", " ")
                method_str = tx.get("payment_method", "")
                st.caption(f"**Paid At:** {paid_str} via {method_str}")
            if tx.get("reference_number"):
                st.caption(f"**Ref:** `{tx['reference_number']}`")
            if tx.get("notes"):
                st.caption(f"**Notes:** {tx['notes']}")

            tc1, tc2, tc3 = st.columns(3)
            if tx.get("status") != "paid" and tc1.button("Mark Paid", key=f"btn_pay_tx_{tx_id}"):
                update_billing_transaction(tx_id, {"status": "paid"})
                st.success(f"Transaction {tx_id} marked as paid.")
                st.rerun()
            if tx.get("status") != "waived" and tc2.button("Waive", key=f"btn_waive_tx_{tx_id}"):
                update_billing_transaction(tx_id, {"status": "waived"})
                st.info(f"Transaction {tx_id} waived.")
                st.rerun()
            if tc3.button("Delete", key=f"btn_del_tx_{tx_id}"):
                delete_billing_transaction(tx_id)
                st.warning(f"Transaction {tx_id} deleted.")
                st.rerun()


def _render_record_payment_tab():
    st.markdown("##### 💳 Record Resident Payment")
    tenants_resp = list_tenants(limit=100)
    tenants_list = tenants_resp.get("items", []) if tenants_resp else []
    if not tenants_list:
        st.caption("No tenants registered.")
        return

    tenant_map = {
        t["id"]: f"{t['first_name']} {t['last_name']} (Bal: ${t.get('balance_due', 0):,.2f})"
        for t in tenants_list
    }
    chosen_tid = st.selectbox(
        "Resident Account",
        options=list(tenant_map.keys()),
        format_func=lambda x: tenant_map.get(x, x),
        key="pay_board_tenant_select",
    )
    sel_tenant: dict[str, Any] = next((t for t in tenants_list if t["id"] == chosen_tid), {})
    default_amt = max(
        1.0, float(sel_tenant.get("balance_due") or sel_tenant.get("monthly_rent", 1000.0))
    )

    c_p1, c_p2 = st.columns(2)
    pay_amt = c_p1.number_input(
        "Payment Amount ($)", min_value=1.0, value=default_amt, step=50.0, key="pay_board_amt"
    )
    pay_meth = c_p2.selectbox(
        "Method",
        [
            "online_portal",
            "ach",
            "credit_card",
            "debit_card",
            "check",
            "cashier_check",
            "money_order",
        ],
        key="pay_board_meth",
    )
    pay_ref = st.text_input(
        "Reference Number / Check #", placeholder="e.g. ACH-44122", key="pay_board_ref"
    )
    pay_memo = st.text_input(
        "Payment Memo", value="Monthly Rent Payment", key="pay_board_memo"
    )

    if st.button("Process Payment", key="btn_board_process_payment"):
        with st.spinner("Recording payment..."):
            payload = {
                "amount": float(pay_amt),
                "payment_method": pay_meth,
                "reference_number": pay_ref.strip(),
                "description": pay_memo.strip(),
            }
            res = record_tenant_payment(chosen_tid, payload)
            if res:
                new_bal = res.get("new_balance", 0.0)
                st.success(
                    f"Payment of ${pay_amt:,.2f} recorded! New balance: ${new_bal:,.2f}"
                )
                st.rerun()
            else:
                st.error("Failed to process payment.")


def _render_post_charge_tab():
    st.markdown("##### 📝 Post Charge / Assessment")
    tenants_resp = list_tenants(limit=100)
    tenants_list = tenants_resp.get("items", []) if tenants_resp else []
    if not tenants_list:
        st.caption("No tenants registered.")
        return

    tenant_map = {
        t["id"]: f"{t['first_name']} {t['last_name']} (Unit: {t.get('unit_id', 'None')})"
        for t in tenants_list
    }
    chosen_tid = st.selectbox(
        "Target Resident",
        options=list(tenant_map.keys()),
        format_func=lambda x: tenant_map.get(x, x),
        key="charge_board_tenant_select",
    )
    sel_tenant: dict[str, Any] = next((t for t in tenants_list if t["id"] == chosen_tid), {})
    sel_unit = sel_tenant.get("unit_id") or "unit_101"

    c_c1, c_c2 = st.columns(2)
    chg_type = c_c1.selectbox(
        "Charge Type",
        [
            "rent",
            "security_deposit",
            "late_fee",
            "utility",
            "parking_fee",
            "pet_rent",
            "maintenance_charge",
        ],
        key="charge_board_type",
    )
    chg_amt = c_c2.number_input(
        "Amount ($)", min_value=1.0, value=50.0, step=10.0, key="charge_board_amt"
    )
    chg_desc = st.text_input(
        "Description",
        placeholder="e.g. Utility Assessment - Water & Sewer",
        key="charge_board_desc",
    )
    chg_due = st.text_input(
        "Due Date (YYYY-MM-DD)", value="2026-11-01", key="charge_board_due"
    )

    if st.button("Post Charge to Ledger", key="btn_board_post_charge"):
        if not chg_desc.strip():
            st.error("Charge description is required.")
        else:
            with st.spinner("Posting transaction to ledger..."):
                payload = {
                    "tenant_id": chosen_tid,
                    "unit_id": sel_unit,
                    "description": chg_desc.strip(),
                    "amount": float(chg_amt),
                    "transaction_type": chg_type,
                    "status": "posted",
                    "due_date": chg_due.strip(),
                }
                res = create_billing_transaction(payload)
                if res:
                    st.success(
                        f"Charge of ${chg_amt:,.2f} posted to tenant {chosen_tid}!"
                    )
                    st.rerun()
                else:
                    st.error("Failed to post charge.")


def _render_billing_metrics_tab(metrics: dict):
    st.markdown("##### 📈 Portfolio Financial Health")
    c1, c2 = st.columns(2)
    c1.metric("Overdue Invoices", metrics.get("overdue_transactions_count", 0))
    c2.metric("Delinquent Tenants", metrics.get("overdue_tenants_count", 0))

    st.markdown("**Revenue by Transaction Type:**")
    for t_name, count in (metrics.get("by_type") or {}).items():
        st.caption(f"- **{t_name.title()}**: {count} transaction(s)")

    st.markdown("**Transaction Status Breakdown:**")
    for s_name, count in (metrics.get("by_status") or {}).items():
        st.caption(f"- **{s_name.title()}**: {count}")


def _render_lease_renewals_board():  # noqa: PLR0912, PLR0915
    with st.sidebar.expander("📝 Lease Renewals & Documents"):
        lr_tab = st.radio(
            "Renewal Section",
            ["Offers", "New Offer", "Portfolio Metrics"],
            horizontal=True,
            key="lr_board_tab_radio",
        )

        if lr_tab == "Offers":
            col_f1, col_f2 = st.columns(2)
            status_filter = col_f1.selectbox(
                "Filter Status",
                ["All", "draft", "offered", "accepted", "signed", "declined", "expired"],
                key="lr_status_filter",
            )
            term_filter = col_f2.selectbox(
                "Filter Term",
                ["All", "6 mos", "12 mos", "18 mos", "24 mos"],
                key="lr_term_filter",
            )

            status_param = None if status_filter == "All" else status_filter
            renewals_resp = list_lease_renewals(status=status_param, limit=50)
            renewals = renewals_resp.get("items", []) if renewals_resp else []

            if term_filter != "All":
                selected_term = int(term_filter.split()[0])
                renewals = [r for r in renewals if r.get("term_months") == selected_term]

            if not renewals:
                st.info("No lease renewal agreements match the current filter.")
            else:
                st.caption(f"Showing **{len(renewals)}** renewal agreement(s)")
                for r in renewals:
                    status = r.get("status", "draft")
                    status_emoji = {
                        "offered": "📄",
                        "signed": "✅",
                        "accepted": "👍",
                        "draft": "📝",
                        "declined": "❌",
                        "expired": "⌛",
                    }.get(status, "📄")

                    with st.container():
                        st.markdown(
                            f"**{status_emoji} {r.get('id')} — "
                            f"{r.get('tenant_id')} (Unit: {r.get('unit_id')})**"
                        )
                        diff = r.get("proposed_rent", 0.0) - r.get("current_rent", 0.0)
                        diff_str = f"+${diff:,.2f}" if diff >= 0 else f"-${abs(diff):,.2f}"
                        st.caption(
                            f"**Rent:** ${r.get('current_rent', 0):,.2f} ➔ "
                            f"**${r.get('proposed_rent', 0):,.2f}** ({diff_str}) | "
                            f"**Term:** {r.get('term_months')}m | **Status:** `{status}`"
                        )
                        st.caption(
                            f"Dates: {r.get('start_date')} to {r.get('end_date')} | "
                            f"Expires: {r.get('expires_at', '')[:10]}"
                        )

                        action_c1, action_c2, action_c3 = st.columns(3)
                        # Publish to RAG
                        if action_c1.button("📚 Index RAG", key=f"btn_pub_rag_{r.get('id')}"):
                            with st.spinner("Publishing to vector store..."):
                                pub_res = publish_lease_renewal_document(r.get("id"))
                                if pub_res:
                                    st.success("Indexed in RAG store!")
                                else:
                                    st.error("Failed to index.")

                        # E-Sign if offered or accepted
                        if (
                            status in ("offered", "accepted")
                            and action_c2.button("✍️ E-Sign", key=f"btn_sign_table_{r.get('id')}")
                        ):
                            sign_res = sign_lease_renewal(
                                r["id"],
                                {
                                    "signature_name": "Resident E-Sign",
                                    "signature_ip": "127.0.0.1",
                                    "notes": "Signed via Lease Renewals management board",
                                },
                            )
                            if sign_res:
                                st.success(f"Renewal {r.get('id')} digitally executed!")
                                st.rerun()

                        # Delete
                        if action_c3.button(
                            "🗑️", key=f"btn_del_lr_{r.get('id')}"
                        ) and delete_lease_renewal(r["id"]):
                            st.success("Renewal deleted.")
                            st.rerun()

                        st.divider()

        elif lr_tab == "New Offer":
            st.markdown("##### Create Manual Renewal Offer")
            all_tenants = list_tenants(limit=100)
            t_items = all_tenants.get("items", []) if all_tenants else []
            t_map = {t["id"]: f"{t['first_name']} {t['last_name']} ({t['id']})" for t in t_items}

            sel_t = st.selectbox(
                "Select Resident",
                options=list(t_map.keys()),
                format_func=lambda x: t_map.get(x, x),
                key="manual_lr_tenant",
            )
            col_p1, col_p2 = st.columns(2)
            manual_prop_rent = col_p1.number_input(
                "Proposed Rent ($)",
                min_value=1.0,
                value=1500.0,
                step=25.0,
                key="manual_lr_prop_rent",
            )
            manual_term = col_p2.selectbox(
                "Term Months", [6, 12, 18, 24], index=1, key="manual_lr_term"
            )
            col_c1, col_c2 = st.columns(2)
            manual_conc = col_c1.number_input(
                "Concession Credit ($)", min_value=0.0, value=0.0, step=50.0, key="manual_lr_conc"
            )
            manual_dep = col_c2.number_input(
                "Deposit Adjustment ($)", value=0.0, step=50.0, key="manual_lr_dep"
            )
            manual_notes = st.text_area(
                "Notes", placeholder="Optional renewal notes", key="manual_lr_notes"
            )

            if st.button("📄 Dispatch Renewal Offer", key="btn_dispatch_manual_lr") and sel_t:
                with st.spinner("Dispatching offer..."):
                    t_obj = next((t for t in t_items if t["id"] == sel_t), None)
                    unit_val = t_obj.get("unit_id") if t_obj else None
                    curr_val = (
                        float(t_obj.get("monthly_rent", 1000.0)) if t_obj else 1000.0
                    )
                    create_res = create_lease_renewal(
                        {
                            "tenant_id": sel_t,
                            "unit_id": unit_val,
                            "proposed_rent": float(manual_prop_rent),
                            "current_rent": curr_val,
                            "term_months": int(manual_term),
                            "concession_amount": float(manual_conc),
                            "security_deposit_change": float(manual_dep),
                            "notes": manual_notes.strip(),
                            "status": "offered",
                        }
                    )
                    if create_res:
                        new_id = create_res.get("renewal", {}).get("id", "")
                        st.success(f"Offer created! ID: {new_id}")
                        st.rerun()
                    else:
                        st.error("Failed to create offer.")

        else:
            st.markdown("##### Portfolio Renewal Conversion Analytics")
            m = get_lease_renewal_metrics()
            if m:
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Total Offers", m.get("total_renewals", 0))
                mc2.metric("Executed", m.get("signed_renewals", 0))
                mc3.metric("Renewal Rate", f"{m.get('renewal_rate', 0.0):.1f}%")

                st.caption(
                    f"**Average Rent Increase:** {m.get('avg_rent_increase_pct', 0.0):.2f}%"
                )

                st.markdown("**Status Distribution:**")
                for st_name, count in (m.get("by_status") or {}).items():
                    st.caption(f"- **{st_name.title()}**: {count}")

                st.markdown("**Term Preference:**")
                for term_name, count in (m.get("by_term") or {}).items():
                    st.caption(f"- **{term_name}**: {count}")


def _render_punchlist_deficiencies(insp_id: str, items: list):
    deficiencies = [
        it
        for it in items
        if isinstance(it, dict)
        and (
            it.get("has_damage")
            or it.get("condition") in ("poor", "damaged")
            or it.get("requires_repair")
        )
    ]
    if not deficiencies:
        return

    st.markdown(f"**Punchlist Deficiencies ({len(deficiencies)}):**")
    for d_item in deficiencies:
        d_id = d_item.get("id", "item")
        d_name = d_item.get("item_name") or d_item.get("name") or "Deficiency"
        d_room = d_item.get("room") or "General"
        d_cost = d_item.get("estimated_cost", 0.0)
        col_d1, col_d2 = st.columns(2)
        col_d1.caption(f"• **[{d_room}] {d_name}** (${d_cost:,.2f})")
        if col_d2.button("🛠️ WO", key=f"btn_wo_{insp_id}_{d_id}"):
            with st.spinner("Dispatching punchlist work order..."):
                wo_res = convert_inspection_item_to_work_order(
                    insp_id, {"item_id": d_id}
                )
                if wo_res:
                    st.success("Work order dispatched!")
                    st.rerun()
                else:
                    st.error("Failed to convert punchlist item.")


def _render_inspection_actions(insp_id: str, istatus: str):
    act_c1, act_c2, act_c3 = st.columns(3)
    if istatus == "scheduled" and act_c1.button(
        "▶️ Start", key=f"btn_start_insp_{insp_id}"
    ):
        with st.spinner("Starting inspection..."):
            if update_inspection(insp_id, {"status": "in_progress"}):
                st.success("Inspection in progress.")
                st.rerun()
            else:
                st.error("Failed to start inspection.")

    if istatus in ("scheduled", "in_progress") and act_c2.button(
        "✅ Complete", key=f"btn_comp_insp_{insp_id}"
    ):
        with st.spinner("Finalizing inspection & deposit..."):
            comp_res = complete_inspection(
                insp_id,
                {
                    "security_deposit_base": 1500.0,
                    "overall_condition": "good",
                },
            )
            if comp_res:
                st.success("Inspection completed and deposit settled!")
                st.rerun()
            else:
                st.error("Failed to complete inspection.")

    if act_c3.button("📚 Index RAG", key=f"btn_pub_rag_insp_{insp_id}"):
        with st.spinner("Indexing inspection report in RAG..."):
            if publish_inspection_document(insp_id):
                st.success("Indexed in RAG store!")
            else:
                st.error("Failed to index report.")

    if st.button("🗑️ Delete Inspection", key=f"btn_del_insp_{insp_id}"):
        if delete_inspection(insp_id):
            st.success("Inspection deleted.")
            st.rerun()
        else:
            st.error("Failed to delete inspection.")


def _render_inspection_records_tab():
    st.markdown("##### Resident Inspection Records & Punchlists")
    col_f1, col_f2 = st.columns(2)
    status_filter = col_f1.selectbox(
        "Status",
        ["All", "scheduled", "in_progress", "completed", "cancelled"],
        key="filter_insp_status",
    )
    type_filter = col_f2.selectbox(
        "Type",
        [
            "All",
            "move_in",
            "move_out",
            "pre_move_out",
            "annual",
            "turnover_punchlist",
        ],
        key="filter_insp_type",
    )

    status_param = None if status_filter == "All" else status_filter
    type_param = None if type_filter == "All" else type_filter
    params = {}
    if status_param:
        params["status"] = status_param
    if type_param:
        params["inspection_type"] = type_param

    insps_resp = list_inspections(params=params)
    insps = insps_resp.get("items", []) if insps_resp else []

    if not insps:
        st.info("No inspection records match the current filter.")
        return

    st.caption(f"Showing **{len(insps)}** inspection record(s)")
    for insp in insps:
        insp_id = insp.get("inspection_id", "")
        itype = insp.get("inspection_type", "move_out").replace("_", " ").title()
        istatus = insp.get("status", "scheduled")
        status_emoji = {
            "scheduled": "📅",
            "in_progress": "🔍",
            "completed": "✅",
            "cancelled": "❌",
        }.get(istatus, "📋")

        with st.container():
            st.markdown(f"**{status_emoji} {insp_id} — {itype}**")
            st.caption(
                f"**Unit:** {insp.get('unit_id', 'N/A')} | "
                f"**Resident:** {insp.get('tenant_id', 'N/A')} | "
                f"**Status:** `{istatus}`"
            )
            st.caption(
                f"**Date:** {insp.get('scheduled_date') or 'N/A'} | "
                f"**Inspector:** {insp.get('inspector_name') or 'N/A'} | "
                f"**Keys Returned:** {'Yes' if insp.get('keys_returned') else 'No'}"
            )

            est_ded = insp.get("total_estimated_deductions", 0.0)
            act_ded = insp.get("total_actual_deductions", 0.0)
            ref_amt = insp.get("net_deposit_refund", 0.0)
            st.caption(
                f"**Est. Deductions:** ${est_ded:,.2f} | "
                f"**Actual:** ${act_ded:,.2f} | "
                f"**Refund:** ${ref_amt:,.2f}"
            )

            _render_punchlist_deficiencies(insp_id, insp.get("items") or [])
            _render_inspection_actions(insp_id, istatus)
            st.divider()


def _render_schedule_inspection_tab():
    st.markdown("##### Schedule Move-In/Move-Out Inspection")
    all_tenants = list_tenants(limit=100)
    t_items = all_tenants.get("items", []) if all_tenants else []
    t_map = {t["id"]: f"{t['first_name']} {t['last_name']} ({t['id']})" for t in t_items}

    sel_t = st.selectbox(
        "Select Resident",
        options=list(t_map.keys()),
        format_func=lambda x: t_map.get(x, x),
        key="manual_insp_tenant",
    )
    t_obj = next((t for t in t_items if t["id"] == sel_t), None)
    unit_val = t_obj.get("unit_id") if t_obj else "unit_101"

    col_t1, col_t2 = st.columns(2)
    manual_itype = col_t1.selectbox(
        "Inspection Type",
        ["move_in", "move_out", "pre_move_out", "annual", "turnover_punchlist"],
        format_func=lambda x: x.replace("_", " ").title(),
        key="manual_insp_type",
    )
    manual_date = col_t2.text_input(
        "Date (YYYY-MM-DD)", value="2026-10-25", key="manual_insp_date"
    )

    col_i1, col_i2 = st.columns(2)
    manual_inspector = col_i1.text_input(
        "Inspector", value="Property Operations Specialist", key="manual_insp_agent"
    )
    manual_dep_base = col_i2.number_input(
        "Base Security Deposit ($)",
        min_value=0.0,
        value=1500.0,
        step=50.0,
        key="manual_insp_dep",
    )
    manual_notes = st.text_area(
        "Notes", placeholder="Optional inspection notes", key="manual_insp_notes"
    )

    if st.button("📋 Schedule Inspection", key="btn_dispatch_manual_insp") and sel_t:
        with st.spinner("Scheduling inspection..."):
            create_res = create_inspection(
                {
                    "tenant_id": sel_t,
                    "unit_id": unit_val,
                    "inspection_type": manual_itype,
                    "scheduled_date": manual_date.strip() if manual_date.strip() else None,
                    "inspector_name": (
                        manual_inspector.strip() if manual_inspector.strip() else None
                    ),
                    "security_deposit_base": float(manual_dep_base),
                    "notes": manual_notes.strip(),
                    "status": "scheduled",
                }
            )
            if create_res:
                new_id = create_res.get("inspection", {}).get("inspection_id", "")
                st.success(f"Inspection scheduled! ID: {new_id}")
                st.rerun()
            else:
                st.error("Failed to schedule inspection.")


def _render_inspection_metrics_tab():
    st.markdown("##### Portfolio Turnover & Inspection Analytics")
    m = get_inspection_metrics()
    if not m:
        st.info("No inspection metrics available.")
        return

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Inspections", m.get("total_inspections", 0))
    dep_summary = m.get("deposit_accounting_summary") or {}
    mc2.metric(
        "Total Deductions", f"${dep_summary.get('total_estimated_deductions', 0.0):,.2f}"
    )
    mc3.metric(
        "Total Refunds", f"${dep_summary.get('total_refund_amounts', 0.0):,.2f}"
    )

    punch_summary = m.get("turnover_punchlist_summary") or {}
    st.caption(
        f"**Turnover Punchlist Items:** {punch_summary.get('total_punchlist_items', 0)} total | "
        f"**Converted to WOs:** {punch_summary.get('total_converted_to_work_orders', 0)} | "
        f"**Pending:** {punch_summary.get('pending_punchlist_actions', 0)}"
    )

    st.markdown("**Status Breakdown:**")
    for st_name, count in (m.get("status_distribution") or {}).items():
        st.caption(f"- **{st_name.title()}**: {count}")

    st.markdown("**Type Breakdown:**")
    for type_name, count in (m.get("type_distribution") or {}).items():
        st.caption(f"- **{type_name.replace('_', ' ').title()}**: {count}")


def _render_inspections_board():
    with st.sidebar.expander("📋 Move-In/Out & Inspections"):
        insp_tab = st.radio(
            "Inspections View",
            ["Inspection Records", "Schedule Inspection", "Portfolio Turnover Metrics"],
            horizontal=True,
            key="insp_board_tab_radio",
        )

        if insp_tab == "Inspection Records":
            _render_inspection_records_tab()
        elif insp_tab == "Schedule Inspection":
            _render_schedule_inspection_tab()
        else:
            _render_inspection_metrics_tab()


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
    _render_tenant_and_property_directory()
    _render_maintenance_board()
    _render_billing_board()
    _render_lease_renewals_board()
    _render_inspections_board()
    _render_knowledge_studio()
    _render_ops_metrics()



