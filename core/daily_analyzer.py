# core/daily_analyzer.py
"""
PulseViper Daily Analyzer
Runs at midnight to:
  1. Analyze yesterday's trades (good vs bad, best/worst setups)
  2. Generate a human-readable daily report saved to logs/daily_reports/
  3. Automatically adjust strategy filters based on patterns seen
"""
import os
import logging
from datetime import date, timedelta, datetime
from typing import Dict, List

from core.trade_journal import trade_journal


class DailyAnalyzer:
    def __init__(self, pattern_learner=None):
        self.logger = logging.getLogger("PulseViper.DailyAnalyzer")
        self.pattern_learner = pattern_learner  # Reference to live PatternLearner
        os.makedirs("logs/daily_reports", exist_ok=True)

    def analyze_yesterday(self) -> Dict:
        """Run full analysis of yesterday's trades. Returns analysis dict."""
        yesterday = date.today() - timedelta(days=1)
        return self.analyze_date(yesterday)

    def analyze_date(self, target_date: date) -> Dict:
        """Analyze trades for any given date and save a report."""
        summary = trade_journal.get_daily_summary(target_date)
        trades = trade_journal.get_trades_for_date(target_date)

        if summary.get("trades", 0) == 0:
            self.logger.info(f"📋 DailyAnalyzer: No trades recorded on {target_date}. Skipping.")
            return {"date": str(target_date), "message": "No trades"}

        # Identify best and worst setups
        setup_stats = summary.get("setup_breakdown", {})
        best_setup = max(setup_stats.items(), key=lambda x: x[1]["pnl"], default=("N/A", {}))
        worst_setup = min(setup_stats.items(), key=lambda x: x[1]["pnl"], default=("N/A", {}))

        # Identify worst individual trade
        worst_trade = min(trades, key=lambda t: float(t.get("pnl", 0)), default=None)
        best_trade = max(trades, key=lambda t: float(t.get("pnl", 0)), default=None)

        # Build report text
        lines = [
            f"{'='*60}",
            f"  PULSEVIPER DAILY PERFORMANCE REPORT — {target_date}",
            f"{'='*60}",
            f"",
            f"📊 SUMMARY",
            f"  Total Trades   : {summary['trades']}",
            f"  Win Rate       : {summary.get('win_rate', 0):.1f}%",
            f"  Total PnL      : ${summary['total_pnl']:.2f}",
            f"  Gross Profit   : ${summary.get('gross_profit', 0):.2f}",
            f"  Gross Loss     : ${summary.get('gross_loss', 0):.2f}",
            f"  Profit Factor  : {summary.get('profit_factor', 0):.2f}",
            f"  Avg RR Achieved: {summary.get('avg_rr', 0):.2f}R",
            f"  TP Hits        : {summary.get('tp_hits', 0)} | SL Hits: {summary.get('sl_hits', 0)}",
            f"  Good Trades    : {summary.get('good_trades', 0)} | Bad: {summary.get('bad_trades', 0)}",
            f"",
            f"🏆 BEST SETUP: {best_setup[0]} (PnL=${best_setup[1].get('pnl', 0):.2f}, "
            f"Wins={best_setup[1].get('wins', 0)}/{best_setup[1].get('count', 0)})",
            f"💀 WORST SETUP: {worst_setup[0]} (PnL=${worst_setup[1].get('pnl', 0):.2f}, "
            f"Wins={worst_setup[1].get('wins', 0)}/{worst_setup[1].get('count', 0)})",
            f"",
        ]

        if best_trade:
            lines.append(f"✅ BEST TRADE: {best_trade.get('action')} {best_trade.get('symbol')} "
                         f"@ {best_trade.get('entry_price')} → ${float(best_trade.get('pnl',0)):.2f} "
                         f"({best_trade.get('close_reason')}) [{best_trade.get('setup_type')}]")
        if worst_trade:
            lines.append(f"❌ WORST TRADE: {worst_trade.get('action')} {worst_trade.get('symbol')} "
                         f"@ {worst_trade.get('entry_price')} → ${float(worst_trade.get('pnl',0)):.2f} "
                         f"({worst_trade.get('close_reason')}) [{worst_trade.get('setup_type')}]")

        lines.extend([
            f"",
            f"📋 SETUP BREAKDOWN",
        ])
        for setup_name, stats in setup_stats.items():
            wr = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
            lines.append(f"  {setup_name:20s}: {stats['count']} trades, {wr:.0f}% WR, PnL=${stats['pnl']:.2f}")

        lines.extend([
            f"",
            f"📝 INDIVIDUAL TRADES",
        ])
        for t in trades:
            cl = t.get("classification", "?")
            badge = "✅" if cl == "GOOD" else "❌"
            lines.append(
                f"  {badge} {t.get('time','')} | {t.get('action',''):4s} | "
                f"Entry={t.get('entry_price','')} Close={t.get('close_price','')} "
                f"PnL=${float(t.get('pnl',0)):.2f} | {t.get('close_reason','')} | {t.get('classification_reason','')}"
            )

        # === Auto-adjustment logic ===
        adjustments = []
        lines.append(f"\n🤖 AUTO-ADJUSTMENTS MADE")

        # Disable bad setups from settings if win rate < 30%
        from utils.settings_manager import settings_manager
        disabled_setups = list(settings_manager.get("disabled_setups", []))
        newly_disabled = []
        newly_enabled = []

        for setup_name, stats in setup_stats.items():
            if stats["count"] < 15:
                continue  # Insufficient data
            
            smoothed_wr = (stats["wins"] + 1) / (stats["count"] + 2)
            if smoothed_wr < 0.30 and setup_name not in disabled_setups:
                disabled_setups.append(setup_name)
                newly_disabled.append(setup_name)
                adjustments.append(f"  ⛔ [RECOMMENDED RECOMMENDATION] Disable setup: {setup_name} (Smoothed WR={smoothed_wr*100:.1f}%)")
            elif smoothed_wr >= 0.60 and setup_name in disabled_setups:
                disabled_setups.remove(setup_name)
                newly_enabled.append(setup_name)
                adjustments.append(f"  ✅ [RECOMMENDED RECOMMENDATION] Re-enable setup: {setup_name} (Smoothed WR={smoothed_wr*100:.1f}%)")

        # Shadow mode: do not write to settings manager directly
        # if newly_disabled or newly_enabled:
        #     settings_manager.set("disabled_setups", disabled_setups)

        # Auto-adjust min_rr_ratio if avg achieved RR differs significantly
        avg_rr = summary.get("avg_rr", 2.0)
        current_rr = settings_manager.get("min_rr_ratio", 2.0)
        if summary.get("wins", 0) >= 3 and abs(avg_rr - current_rr) > 0.4:
            new_rr = round(max(1.5, min(3.5, (avg_rr + current_rr) / 2)), 1)
            if new_rr != current_rr:
                # Shadow mode: do not write to settings manager directly
                # settings_manager.set("min_rr_ratio", new_rr)
                adjustments.append(f"  📐 [RECOMMENDED RECOMMENDATION] Adjust min_rr_ratio: {current_rr} → {new_rr} (avg achieved={avg_rr:.2f}R)")

        if not adjustments:
            lines.append("  No auto-adjustments needed today.")
        else:
            lines.extend(adjustments)

        lines.append(f"\n{'='*60}")
        report_text = "\n".join(lines)

        # Save report
        report_path = f"logs/daily_reports/{target_date}.txt"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            self.logger.info(f"📋 Daily report saved: {report_path}")
        except Exception as e:
            self.logger.error(f"Failed to save daily report: {e}")

        print(report_text)  # Also print to log output

        return {
            "date": str(target_date),
            "summary": summary,
            "best_setup": best_setup[0],
            "worst_setup": worst_setup[0],
            "adjustments": adjustments,
            "report_path": report_path,
            "report_text": report_text
        }

    def get_latest_report(self) -> str:
        """Return the text of the most recent daily report."""
        reports_dir = "logs/daily_reports"
        if not os.path.exists(reports_dir):
            return "No reports yet."
        files = sorted(
            [f for f in os.listdir(reports_dir) if f.endswith(".txt")],
            reverse=True
        )
        if not files:
            return "No reports yet."
        try:
            with open(os.path.join(reports_dir, files[0]), "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "Failed to read report."

    def get_report_for_date(self, target_date: date) -> str:
        """Return report for a specific date if it exists."""
        path = f"logs/daily_reports/{target_date}.txt"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return "Failed to read report."
        return f"No report found for {target_date}"
