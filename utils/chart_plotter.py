# utils/chart_plotter.py
import os
import time
import logging
import pandas as pd
import numpy as np

# Set matplotlib backend to Agg to prevent GUI popups
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger("PulseViper.ChartPlotter")

def save_visual_chart(filename_prefix: str, df: pd.DataFrame, entry_price: float, sl: float, tp: float, action: str, symbol: str, extra_title: str = "") -> str:
    """
    Generates a dark-themed visual candlestick chart of the setup/trade and saves it as a PNG.
    Position tool (Long/Short box) and PnL badges are ONLY drawn starting from the specific entry candle
    when an active trade entry is placed.
    """
    try:
        os.makedirs("logs/charts", exist_ok=True)
        
        # Take the last 40 bars for a clean chart
        plot_df = df.tail(40).copy()
        if len(plot_df) == 0:
            return ""
            
        fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
        plt.style.use('dark_background')
        fig.patch.set_facecolor('#111219')
        ax.set_facecolor('#151821')
        
        # Plot Support & Resistance lines if they exist and are valid
        if 'support' in plot_df.columns and plot_df['support'].iloc[-1] > 0:
            ax.axhline(y=plot_df['support'].iloc[-1], color='#00ffcc', linestyle='--', alpha=0.6, linewidth=1.5, label='Support')
        if 'resistance' in plot_df.columns and plot_df['resistance'].iloc[-1] > 0:
            ax.axhline(y=plot_df['resistance'].iloc[-1], color='#ff3366', linestyle='--', alpha=0.6, linewidth=1.5, label='Resistance')
            
        # Draw Candlesticks
        for i in range(len(plot_df)):
            row = plot_df.iloc[i]
            color = '#26a69a' if row['close'] >= row['open'] else '#ef5350'
            # Wick
            ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1.8)
            # Body
            bottom = min(row['open'], row['close'])
            height = max(abs(row['open'] - row['close']), 0.00001)
            rect = plt.Rectangle((i - 0.35, bottom), 0.7, height, facecolor=color, edgecolor=color)
            ax.add_patch(rect)

            # Draw active Order Block (OB) zones if present in columns
            if 'ob_top' in row and 'ob_bottom' in row and not np.isnan(row['ob_top']) and not np.isnan(row['ob_bottom']):
                ob_rect = plt.Rectangle((i - 0.45, row['ob_bottom']), 0.9, max(row['ob_top'] - row['ob_bottom'], 0.01),
                                        facecolor='#ff9900', alpha=0.2, edgecolor='#ff9900', linewidth=0.8)
                ax.add_patch(ob_rect)

            # Draw active Fair Value Gap (FVG) zones if present
            if 'fvg_top' in row and 'fvg_bottom' in row and not np.isnan(row['fvg_top']) and not np.isnan(row['fvg_bottom']):
                fvg_rect = plt.Rectangle((i - 0.45, row['fvg_bottom']), 0.9, max(row['fvg_top'] - row['fvg_bottom'], 0.01),
                                         facecolor='#00e5ff', alpha=0.25, edgecolor='#00e5ff', linewidth=0.8)
                ax.add_patch(fvg_rect)

            # Draw Market Structure Shift (MSS) / CHoCH indicators (large 12pt bold font)
            if 'mss_signal' in row and row['mss_signal'] != 0:
                mss_color = '#00ff88' if row['mss_signal'] > 0 else '#ff0055'
                mss_label = "▲ MSS BUY" if row['mss_signal'] > 0 else "▼ MSS SELL"
                y_pos = row['low'] - 0.4 if row['mss_signal'] > 0 else row['high'] + 0.4
                ax.text(i, y_pos, mss_label, color=mss_color, fontsize=12, fontweight='bold', ha='center')

            # Draw Liquidity Sweep markers (large 12pt bold font)
            if 'sweep_type' in row and row['sweep_type'] != 0:
                swp_color = '#ffcc00'
                swp_label = "★ SWEEP"
                y_pos = row['low'] - 0.8 if row['sweep_type'] > 0 else row['high'] + 0.8
                ax.text(i, y_pos, swp_label, color=swp_color, fontsize=12, fontweight='bold', ha='center')
            
        act_upper = action.upper() if isinstance(action, str) else str(action or "").upper()
        is_active_entry = act_upper in ('BUY', 'SELL') and entry_price > 0 and sl > 0 and tp > 0
        if is_active_entry:
            # Position tool starts at the entry candle (last 10 bars) and spans to the right
            entry_idx = max(0, len(plot_df) - 10)
            x_start = entry_idx - 0.4
            x_end = len(plot_df) - 0.1
            width = x_end - x_start

            risk_dist = abs(entry_price - sl)
            reward_dist = abs(tp - entry_price)
            rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0.0

            if act_upper == 'BUY':
                # Green Reward Box
                rect_tp = plt.Rectangle((x_start, entry_price), width, tp - entry_price,
                                        facecolor='#00e676', alpha=0.25, edgecolor='#00e676', linewidth=1.5)
                # Red Risk Box
                rect_sl = plt.Rectangle((x_start, sl), width, entry_price - sl,
                                        facecolor='#ff1744', alpha=0.25, edgecolor='#ff1744', linewidth=1.5)
                ax.add_patch(rect_tp)
                ax.add_patch(rect_sl)
            else: # SELL
                # Green Reward Box
                rect_tp = plt.Rectangle((x_start, tp), width, entry_price - tp,
                                        facecolor='#00e676', alpha=0.25, edgecolor='#00e676', linewidth=1.5)
                # Red Risk Box
                rect_sl = plt.Rectangle((x_start, entry_price), width, sl - entry_price,
                                        facecolor='#ff1744', alpha=0.25, edgecolor='#ff1744', linewidth=1.5)
                ax.add_patch(rect_tp)
                ax.add_patch(rect_sl)

            # Draw crisp horizontal lines starting at entry candle
            ax.hlines(y=entry_price, xmin=x_start, xmax=x_end, color='#ffc107', linestyle='-', linewidth=2.2, label=f'Entry: {entry_price:.2f}')
            ax.hlines(y=sl, xmin=x_start, xmax=x_end, color='#ff1744', linestyle='--', linewidth=2.0, label=f'SL: {sl:.2f}')
            ax.hlines(y=tp, xmin=x_start, xmax=x_end, color='#00e676', linestyle='--', linewidth=2.0, label=f'TP: {tp:.2f}')

            # Add prominent, large 13pt bold PnL and Risk-Reward badges on the position box
            ax.text(x_start + width * 0.5, (entry_price + tp) / 2.0, f"TARGET TP (+{rr_ratio:.2f}R)",
                    color='#ffffff', fontsize=13, fontweight='bold', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#00c853', alpha=0.85, edgecolor='none'))
            ax.text(x_start + width * 0.5, (entry_price + sl) / 2.0, f"STOP LOSS (-1.00R)",
                    color='#ffffff', fontsize=13, fontweight='bold', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#d50000', alpha=0.85, edgecolor='none'))

        # Set prominent titles and formatting with large font sizes (16pt title, 13pt ticks/legend)
        ax.set_title(f"{symbol} [{action}] - {extra_title}", fontsize=16, color='#ffffff', fontweight='bold', pad=18)
        ax.grid(True, color='#242936', linestyle=':', alpha=0.6)
        
        # Generate x-axis labels with larger font size 12pt bold
        x_ticks = list(range(0, len(plot_df), 5))
        x_labels = []
        for idx in x_ticks:
            t_val = plot_df.index[idx]
            if isinstance(t_val, pd.Timestamp):
                x_labels.append(t_val.strftime("%H:%M"))
            elif hasattr(t_val, 'strftime'):
                x_labels.append(t_val.strftime("%H:%M"))
            else:
                x_labels.append(str(idx))
                
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_labels, color='#d0d4e0', fontsize=12, fontweight='bold')
        ax.tick_params(colors='#d0d4e0', labelsize=13)
        
        # Render Y axis on the right side with larger font size 13pt bold
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        
        # Legend with large, prominent 13pt bold font
        ax.legend(loc='upper left', framealpha=0.45, facecolor='#111219', edgecolor='#8a90a0', fontsize=13)
        
        timestamp = int(time.time())
        filename = f"logs/charts/{filename_prefix}_{timestamp}_{symbol}_{action}.png"
        plt.savefig(filename, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
        plt.close(fig)
        return filename
    except Exception as e:
        logger.error(f"Error saving visual chart: {e}", exc_info=True)
        return ""
