"""FinAI Streamlit app: Chat, Portfolio, Market and Goals tabs.

Memory model (see docs/DESIGN.md):
- st.session_state  = this browser tab's memory across reruns (user_id, current thread_id).
- ProfileStore      = long-term memory per user (profile, holdings, list of chats).
- LangGraph checkpointer = conversation history per thread_id.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.core import services
from src.core.config import SAMPLE_DIR, get_config
from src.utils import tickers
from src.utils.compliance import DISCLAIMER
from src.utils.finance_math import project_goal

HOLDING_COLS = ["symbol", "quantity", "avg_price", "asset_type", "sector", "expense_ratio", "plan", "current_price"]
ASSET_TYPES = ["stock", "etf", "mutual_fund", "equity_fund", "debt_fund", "gold", "cash"]


@st.cache_resource
def get_graph():
    from src.workflow.graph import build_graph
    return build_graph(checkpointer=services.get_checkpointer())


# ---------------------------------------------------------------- session ---
def sign_in(user_id: str) -> None:
    store = services.get_profiles()
    uid = store.normalize_user_id(user_id)
    if not uid:
        st.sidebar.error("Enter a user ID with letters or numbers.")
        return
    profile, holdings = store.load(uid)
    st.session_state.update(user_id=uid, profile=profile, holdings=holdings,
                            thread_id=store.new_thread(uid))  # FR8b: fresh chat per visit


def new_chat() -> None:
    st.session_state.thread_id = services.get_profiles().new_thread(st.session_state.user_id)


def save_user() -> None:
    services.get_profiles().save(st.session_state.user_id, st.session_state.profile, st.session_state.holdings)


def sidebar() -> None:
    st.sidebar.title("FinAI")
    st.sidebar.caption("Learn about money and investing. Education, not advice.")
    if "user_id" not in st.session_state:
        uid = st.sidebar.text_input("Your user ID", placeholder="meena")
        if st.sidebar.button("Continue", type="primary"):
            sign_in(uid)
            st.rerun()
        st.sidebar.info("Use any simple ID. Your profile, holdings and chats are saved under it on this machine.")
        return

    st.sidebar.markdown(f"Signed in as **{st.session_state.user_id}**")
    p = st.session_state.profile
    with st.sidebar.expander("Your profile", expanded=not p.get("age")):
        with st.form("profile_form"):
            p["name"] = st.text_input("Name", p.get("name") or "")
            p["age"] = st.number_input("Age", 16, 100, int(p.get("age") or 30))
            p["monthly_income"] = st.number_input("Monthly income (₹, optional)", 0, 10_000_000,
                                                  int(p.get("monthly_income") or 0), step=5000)
            levels = ["beginner", "intermediate", "advanced"]
            p["knowledge_level"] = st.selectbox("Knowledge level", levels,
                                                levels.index(p.get("knowledge_level", "beginner")))
            risks = ["cautious", "moderate", "aggressive"]
            p["risk_appetite"] = st.selectbox("Risk appetite", risks, risks.index(p.get("risk_appetite", "moderate")))
            p["goals"] = st.text_area("Goals (optional)", p.get("goals") or "", height=68)
            if st.form_submit_button("Save profile"):
                save_user()
                st.success("Profile saved")

    st.sidebar.divider()
    if st.sidebar.button("New conversation", use_container_width=True):
        new_chat()
        st.rerun()
    threads = services.get_profiles().list_threads(st.session_state.user_id)
    if threads:
        st.sidebar.caption("Past chats")
        for t in threads[:15]:
            current = t["thread_id"] == st.session_state.thread_id
            label = ("▸ " if current else "") + t["title"]
            if st.sidebar.button(label, key=f"t-{t['thread_id']}", use_container_width=True, disabled=current):
                st.session_state.thread_id = t["thread_id"]
                st.rerun()
    if st.sidebar.button("Sign out"):
        for k in ("user_id", "profile", "holdings", "thread_id"):
            st.session_state.pop(k, None)
        st.rerun()


# ------------------------------------------------------------------- chat ---
def _src_label(s) -> str:
    if isinstance(s, dict):
        return str(s.get("title") or s.get("source") or s.get("url") or s)
    return str(s)


def _render_trace(graph, config) -> None:
    """Show which agents the router picked and how each got its information (reads graph state)."""
    try:
        snap = graph.get_state(config)
        vals = snap.values if snap else {}
    except Exception:  # noqa: BLE001 - trace is best-effort, never break the answer
        return
    from src.agents.specialists import AGENT_LABELS
    tasks = vals.get("tasks") or []
    outs = vals.get("agent_outputs") or []
    with st.expander("\U0001F50D How I answered this (agent trace)", expanded=False):
        if vals.get("blocked"):
            st.markdown("**Input guard:** blocked this message (prompt-injection rule). No specialists were called.")
            return
        if tasks:
            picked = ", ".join(f"`{t['agent']}`" for t in tasks)
            st.markdown(f"**Router picked:** {picked}" + (" — run in parallel" if len(tasks) > 1 else ""))
            for t in tasks:
                st.caption(f"\u21B3 {t['agent']} \u2190 \"{t.get('query', '')}\"")
        else:
            st.markdown("**Router:** answered directly \u2014 no specialist needed.")
        for o in outs:
            label = AGENT_LABELS.get(o.get("agent"), o.get("agent"))
            st.markdown(f"**{label}** \u2014 {o.get('tool_calls', 0)} tool call(s) \u00B7 status: `{o.get('status')}`")
            srcs = o.get("sources") or []
            if srcs:
                st.caption("sources: " + " \u00B7 ".join(_src_label(x) for x in srcs[:5]))
            unav = o.get("unavailable") or []
            if unav:
                st.caption("could not fetch: " + ", ".join(str(u) for u in unav))
        st.caption("Guard \u2192 Router \u2192 specialists (parallel) \u2192 Synthesizer \u2192 Evaluator \u2192 Finalize")


def chat_tab() -> None:
    graph = get_graph()
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    snapshot = graph.get_state(config)
    messages = (snapshot.values or {}).get("messages", []) if snapshot else []
    if not messages:
        st.markdown("#### Ask me anything about money and investing")
        st.caption("Try: *What is a mutual fund?* · *Is my portfolio too concentrated?* · "
                   "*Price of Infosys and any news on it?* · *I want ₹25 lakh for my daughter's college*")
    for m in messages:
        role = "user" if m.type == "human" else "assistant"
        if m.type in ("human", "ai") and m.content:
            st.chat_message(role).markdown(m.content)

    prompt = st.chat_input("Ask FinAI…")
    if not prompt:
        return
    st.chat_message("user").markdown(prompt)
    if not messages:
        services.get_profiles().rename_thread(st.session_state.thread_id, prompt[:50])
    from src.workflow.graph import run_turn

    with st.chat_message("assistant"):
        answer = ""
        with st.status("Working on your question…", expanded=False) as status:
            try:
                for kind, text in run_turn(graph, st.session_state.thread_id, st.session_state.user_id,
                                           prompt, st.session_state.profile, st.session_state.holdings):
                    if kind == "progress":
                        status.update(label=text + "…")
                        st.write(text)
                    else:
                        answer = text
                status.update(label="Done", state="complete")
            except Exception as e:  # noqa: BLE001
                status.update(label="Something went wrong", state="error")
                st.error(f"FinAI couldn't answer right now ({type(e).__name__}). Check your API key and try again.")
                return
        st.markdown(answer)
        _render_trace(graph, config)


# -------------------------------------------------------------- portfolio ---
def _holdings_df() -> pd.DataFrame:
    return pd.DataFrame(st.session_state.holdings or [], columns=HOLDING_COLS)


def _set_holdings(df: pd.DataFrame) -> None:
    df = df.dropna(subset=["symbol"])
    df = df[df["symbol"].astype(str).str.strip() != ""]
    records = df.astype(object).where(pd.notna(df), None).to_dict("records")
    st.session_state.holdings = records
    save_user()


def portfolio_tab() -> None:
    st.markdown("#### Your holdings")
    st.caption("Enter stocks by NSE symbol or name (e.g. INFY, Infosys). For mutual funds, enter the "
               "fund name, units, average NAV and the latest NAV in current_price.")
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("Load sample: Arjun"):
        _set_holdings(pd.read_csv(SAMPLE_DIR / "arjun.csv"))
        st.rerun()
    if c2.button("Load sample: Vikram"):
        _set_holdings(pd.read_csv(SAMPLE_DIR / "vikram.csv"))
        st.rerun()
    up = c3.file_uploader("Upload CSV", type="csv", label_visibility="collapsed")
    if up is not None and st.button("Use uploaded CSV"):
        df = pd.read_csv(up)
        missing = {"symbol", "quantity", "avg_price"} - set(df.columns)
        if missing:
            st.error(f"CSV needs columns: {', '.join(sorted(missing))}")
        else:
            _set_holdings(df.reindex(columns=HOLDING_COLS))
            st.rerun()

    edited = st.data_editor(
        _holdings_df(), num_rows="dynamic", use_container_width=True, key="holdings_editor",
        column_config={
            "asset_type": st.column_config.SelectboxColumn(options=ASSET_TYPES, default="stock"),
            "plan": st.column_config.SelectboxColumn(options=["", "direct", "regular"]),
            "expense_ratio": st.column_config.NumberColumn(help="% per year, funds/ETFs only"),
        })
    if st.button("Save holdings", type="primary"):
        _set_holdings(edited)
        st.success("Holdings saved. The chat can now use them.")

    if not st.session_state.holdings:
        st.info("Add holdings or load a sample to see the analysis.")
        return
    with st.spinner("Fetching prices…"):
        a = services.analyze_holdings(st.session_state.holdings)
    if a.get("status") != "ok":
        st.warning(a.get("message", "Couldn't analyse these holdings."))
        return
    m = st.columns(4)
    m[0].metric("Total value", f"₹{a['total_value']:,.0f}")
    m[1].metric("Profit / loss", f"₹{a['pnl']:,.0f}", f"{a['pnl_pct']}%")
    m[2].metric("Diversification score", f"{a['diversification_score']}/100")
    m[3].metric("Risk level", a["risk_level"])

    hdf = pd.DataFrame(a["holdings"])
    col1, col2 = st.columns(2)
    col1.plotly_chart(px.pie(hdf, names="symbol", values="value", title="Allocation by holding", hole=0.4),
                      use_container_width=True)
    sec = pd.DataFrame({"sector": list(a["sector_allocation"]), "pct": list(a["sector_allocation"].values())})
    col2.plotly_chart(px.bar(sec, x="sector", y="pct", title="Allocation by sector (%)"), use_container_width=True)

    for f in a["concentration_flags"]:
        what = "one stock" if f["type"] == "single_stock" else "one sector"
        st.warning(f"**{f['name']}** is {f['weight_pct']}% of your portfolio, above the {f['limit_pct']}% "
                   f"guide for {what}. Concentration means one company's or sector's bad news affects a large "
                   "part of your money. This is an educational flag, not a recommendation.")
    if a.get("weighted_expense_ratio_pct") is not None:
        st.info(f"Weighted expense ratio of your funds: **{a['weighted_expense_ratio_pct']}%** a year."
                + (f" Regular plans: {', '.join(a['regular_plan_funds'])}. Regular plans include distributor "
                   "commission, so their expense ratio is higher than the same fund's direct plan."
                   if a["regular_plan_funds"] else ""))
    st.dataframe(hdf[["symbol", "asset_type", "sector", "quantity", "avg_price", "price", "value", "pnl_pct",
                      "weight_pct", "price_basis"]], use_container_width=True, hide_index=True)
    ps = a["price_source"]
    note = f"Prices: {ps['source']}, as of {ps['as_of']}." if ps.get("as_of") else "Live prices unavailable."
    if a["prices_unavailable_for"]:
        note += f" No live price for {', '.join(a['prices_unavailable_for'])}: buy price used."
    st.caption(note + f" {DISCLAIMER}")


# ----------------------------------------------------------------- market ---
def market_tab() -> None:
    market = services.get_market()
    st.markdown("#### Indian market overview")
    cols = st.columns(3)
    for col, (name, tk) in zip(cols, [("Nifty 50", "^NSEI"), ("Sensex", "^BSESN"), ("Bank Nifty", "^NSEBANK")]):
        q = market.get_quote(tk)
        if q.get("price"):
            col.metric(name, f"{q['price']:,.2f}", f"{q['change_pct']}%")
            col.caption(f"{q['note']} As of {q.get('as_of')}")
        else:
            col.metric(name, "—")
            col.caption(q["note"])

    st.markdown("#### Look up a stock or index")
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Name or NSE symbol", placeholder="Infosys, HDFC Bank, TCS, Nifty…")
    period = c2.selectbox("Period", ["5d", "1mo", "3mo", "6mo", "1y", "5y"], index=2)
    if not query:
        return
    r = tickers.resolve(query, get_config()["market"]["exchange_suffix"])
    if r["status"] == "ambiguous":
        st.info("Which one do you mean? " + ", ".join(f"{c['name']} ({c['ticker']})" for c in r["candidates"]))
        return
    if r["status"] == "not_found":
        st.warning("Couldn't find that name. Try the NSE symbol, e.g. INFY.")
        return
    q = market.get_quote(r["ticker"])
    if q.get("price"):
        st.metric(f"{r['name']} ({r['ticker']})", f"₹{q['price']:,.2f}", f"{q['change']} ({q['change_pct']}%)")
    st.caption(f"{q['note']} " + (f"As of {q['as_of']}." if q.get("as_of") else "") + f" Source: {q['source']}.")
    h = market.get_history(r["ticker"], period)
    if h["points"]:
        df = pd.DataFrame(h["points"])
        st.plotly_chart(px.line(df, x="date", y="close", title=f"{r['name']}: closing price, {period} "
                                f"({h.get('change_pct', 0)}%)"), use_container_width=True)
    st.caption(DISCLAIMER)


# ------------------------------------------------------------------ goals ---
def goals_tab() -> None:
    g = get_config()["goals"]
    st.markdown("#### Plan a goal")
    risks = list(g["expected_return_pct"])
    with st.form("goal"):
        c1, c2 = st.columns(2)
        target = c1.number_input("Target amount in today's ₹", 10_000, 1_000_000_000, 2_500_000, step=50_000)
        years = c2.number_input("Years to the goal", 1, 50, 8)
        savings = c1.number_input("Already saved for this goal (₹)", 0, 1_000_000_000, 300_000, step=10_000)
        default_risk = st.session_state.profile.get("risk_appetite", "moderate")
        risk = c2.selectbox("Risk appetite", risks, risks.index(default_risk) if default_risk in risks else 1)
        go = st.form_submit_button("Calculate", type="primary")
    if not go:
        return
    r = project_goal(target, years, savings, risk, g["inflation_pct"], g["expected_return_pct"], g["assumptions_as_of"])
    if r["status"] != "ok":
        st.error(r["message"])
        return
    m = st.columns(3)
    m[0].metric("Monthly SIP needed", f"₹{r['monthly_sip']:,.0f}")
    m[1].metric("Target after inflation", f"₹{r['future_target']:,.0f}")
    m[2].metric("Or lump sum today", f"₹{r['lump_sum_today_instead']:,.0f}")
    df = pd.DataFrame(r["projection"]).melt(id_vars="year", value_vars=["value", "invested"],
                                            var_name="series", value_name="₹")
    st.plotly_chart(px.line(df, x="year", y="₹", color="series", markers=True,
                            title="Projected value vs money invested"), use_container_width=True)
    st.markdown("**Monthly SIP needed by risk appetite:** " +
                " · ".join(f"{k}: ₹{v:,.0f}" for k, v in r["scenarios"].items()))
    st.caption(f"Assumptions: {r['assumptions']} {DISCLAIMER}")


# ------------------------------------------------------------------- main ---
def main() -> None:
    st.set_page_config(page_title="FinAI", page_icon="📈", layout="wide")
    sidebar()
    if "user_id" not in st.session_state:
        st.title("FinAI: your finance learning assistant")
        st.markdown("Enter a user ID in the sidebar to start. FinAI explains concepts, analyses the "
                    "portfolio you enter, shows Indian market data and helps plan goals. "
                    f"_{DISCLAIMER}_")
        return
    tabs = st.tabs(["Chat", "Portfolio", "Market", "Goals"])
    with tabs[0]:
        chat_tab()
    with tabs[1]:
        portfolio_tab()
    with tabs[2]:
        market_tab()
    with tabs[3]:
        goals_tab()
