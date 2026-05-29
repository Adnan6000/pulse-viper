# dashboard/html_template.py

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PULSE VIPER | SMC AI Web Control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #05070c;
            --glass-bg: rgba(13, 20, 38, 0.6);
            --glass-border: rgba(255, 255, 255, 0.05);
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --color-green: #2ecc71;
            --color-red: #ff4757;
            --color-gold: #ffd700;
            --color-blue: #00d2d3;
            --glow-green: rgba(46, 204, 113, 0.15);
            --glow-red: rgba(255, 71, 87, 0.15);
            --glow-blue: rgba(0, 210, 211, 0.15);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            user-select: none;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            overflow-x: hidden;
            min-height: 100vh;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(0, 168, 255, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(0, 240, 118, 0.04) 0%, transparent 40%);
            background-attachment: fixed;
            display: flex;
            flex-direction: column;
        }

        .main-dashboard {
            width: 100%;
            padding: 24px 30px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--glass-border);
            padding-bottom: 16px;
        }

        .logo-section h1 {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: 1px;
            background: linear-gradient(135deg, var(--text-primary) 30%, var(--color-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            padding: 8px 16px;
            border-radius: 30px;
            font-size: 13px;
            font-weight: 600;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--color-green);
            box-shadow: 0 0 10px var(--color-green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.05); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        /* ── Three-Column Main Content Grid ───────────────── */
        .dashboard-container {
            display: grid;
            grid-template-columns: 340px 1fr 340px;
            gap: 20px;
            width: 100%;
        }

        @media (max-width: 1200px) {
            .dashboard-container {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(15px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* ── Interactive Chart Styling ──────────────────── */
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .timeframe-selector, .chart-tools {
            display: flex;
            gap: 6px;
            background: rgba(0, 0, 0, 0.2);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--glass-border);
        }

        .tf-btn, .tool-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .tf-btn:hover, .tf-btn.active, .tool-btn:hover, .tool-btn.active {
            background: var(--color-blue);
            color: var(--bg-dark);
        }

        /* ── Speedometer Sentiment Dials ────────────────── */
        .sentiment-dial-box {
            display: flex;
            flex-direction: column;
            align-items: center;
            background: rgba(0,0,0,0.15);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 12px;
            gap: 6px;
        }

        .dial-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
        }

        .dial-svg-container {
            position: relative;
            width: 70px;
            height: 40px;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: flex-end;
        }

        .dial-svg {
            transform: rotate(-180deg);
            transform-origin: 35px 35px;
        }

        .dial-bg {
            fill: none;
            stroke: rgba(255,255,255,0.05);
            stroke-width: 6;
            stroke-linecap: round;
        }

        .dial-progress {
            fill: none;
            stroke-width: 6;
            stroke-linecap: round;
            stroke-dasharray: 0 190;
            transition: stroke-dasharray 0.5s ease, stroke 0.3s ease;
        }

        .dial-text {
            position: absolute;
            bottom: 0;
            font-size: 11px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .dial-direction {
            font-size: 9px;
            font-weight: 600;
        }

        /* ── News Articles Styling ──────────────────────── */
        .news-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .news-item {
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--glass-border);
            border-radius: 8px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            cursor: pointer;
            transition: border-color 0.2s ease;
        }

        .news-item:hover {
            border-color: rgba(0, 168, 255, 0.3);
        }

        .news-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 10px;
        }

        .news-title {
            font-size: 12px;
            font-weight: 600;
            line-height: 1.3;
        }

        .news-desc {
            font-size: 11px;
            color: var(--text-muted);
            line-height: 1.3;
            display: none;
            margin-top: 4px;
            border-top: 1px solid rgba(255,255,255,0.03);
            padding-top: 4px;
        }

        .news-desc.open {
            display: block;
        }

        .news-item .ticker-badge {
            font-size: 8px;
            padding: 2px 4px;
            border-radius: 3px;
            font-weight: 700;
        }

        .ticker-badge.high { background: rgba(255, 51, 102, 0.2); color: var(--color-red); }
        .ticker-badge.medium { background: rgba(255, 204, 0, 0.2); color: var(--color-gold); }
        .ticker-badge.low { background: rgba(0, 240, 118, 0.2); color: var(--color-green); }

        /* ── Prediction Card & Tables ───────────────────── */
        .prediction-box {
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: rgba(0, 168, 255, 0.03);
            border: 1px solid rgba(0, 168, 255, 0.15);
            border-radius: 12px;
            padding: 14px;
        }

        .pred-row {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            padding-bottom: 5px;
        }

        .pred-row span:last-child {
            font-weight: 600;
        }

        .pred-title {
            font-size: 15px;
            font-weight: 700;
            color: var(--color-blue);
            text-align: center;
        }

        /* Volume Profile POC Chart */
        .vp-chart {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }

        .vp-bar-row {
            display: flex;
            align-items: center;
            height: 10px;
            font-size: 9px;
            gap: 6px;
        }

        .vp-price {
            width: 55px;
            color: var(--text-muted);
            font-family: monospace;
        }

        .vp-bar-fill {
            height: 60%;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 1.5px;
            transition: width 0.3s ease;
        }

        .vp-bar-row.poc .vp-bar-fill {
            background: var(--color-gold);
            box-shadow: 0 0 6px var(--color-gold);
        }

        .vp-bar-row.poc .vp-price {
            color: var(--color-gold);
            font-weight: 700;
        }

        /* Tables */
        .table-wrap {
            overflow-x: auto;
            border: 1px solid var(--glass-border);
            border-radius: 8px;
            background: rgba(0, 0, 0, 0.15);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 11px;
        }

        th {
            background: rgba(255, 255, 255, 0.02);
            color: var(--text-muted);
            font-weight: 600;
            padding: 8px 12px;
            border-bottom: 1px solid var(--glass-border);
        }

        td {
            padding: 8px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            color: var(--text-primary);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.01);
        }

        /* ── Settings Drawer & Gear Overlay ──────────────── */
        .config-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(5px);
            z-index: 1002;
            display: none;
        }

        .config-drawer {
            position: fixed;
            right: -360px;
            top: 0; bottom: 0;
            width: 360px;
            background: rgba(10, 14, 26, 0.98);
            border-left: 1px solid var(--glass-border);
            z-index: 1003;
            transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            overflow-y: auto;
            backdrop-filter: blur(20px);
        }

        .config-drawer.open {
            right: 0;
        }

        .gear-btn {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            width: 40px; height: 40px;
            border-radius: 50%;
            color: var(--text-primary);
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s ease;
        }

        .gear-btn:hover {
            border-color: var(--color-blue);
            color: var(--color-blue);
        }

        .settings-grid {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .setting-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .setting-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .setting-name {
            font-size: 13px;
            font-weight: 600;
        }

        .setting-desc {
            font-size: 11px;
            color: var(--text-muted);
        }

        /* Switches & Sliders */
        .switch {
            position: relative;
            display: inline-block;
            width: 44px; height: 22px;
        }

        .switch input { opacity: 0; width: 0; height: 0; }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(255,255,255,0.1);
            transition: .3s;
            border-radius: 34px;
            border: 1px solid var(--glass-border);
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 14px; width: 14px;
            left: 3px; bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }

        input:checked + .slider { background-color: var(--color-blue); }
        input:checked + .slider:before { transform: translateX(22px); }

        .range-slider-container {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .range-slider-container input[type="range"] {
            flex-grow: 1;
            accent-color: var(--color-blue);
        }

        .mode-selector {
            display: flex;
            gap: 6px;
            background: rgba(0, 0, 0, 0.2);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--glass-border);
        }

        .mode-btn {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .mode-btn.active {
            background: var(--color-blue);
            color: var(--bg-dark);
        }

        .btn-train, .btn-panic {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: background 0.2s ease;
        }

        .btn-train { background: var(--color-blue); color: var(--bg-dark); }
        .btn-train:hover { background: #008cd4; }
        .btn-panic { background: var(--color-red); color: var(--text-primary); }
        .btn-panic:hover { background: #d4204f; }

        /* Ticker Ribbons styling */
        .tickers-container {
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin-top: 12px;
            margin-bottom: 6px;
            width: 100%;
        }
        .ticker-row {
            overflow: hidden;
            white-space: nowrap;
            display: flex;
            align-items: center;
            height: 28px;
            border-radius: 6px;
            border: 1px solid var(--glass-border);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            position: relative;
            background: rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(5px);
        }
        .ticker-row.caution-ticker {
            border-color: rgba(255, 71, 87, 0.25);
            background: rgba(255, 71, 87, 0.15);
            color: var(--color-red);
            text-shadow: 0 0 5px rgba(255, 71, 87, 0.15);
        }
        .ticker-row.news-ticker {
            border-color: rgba(255, 215, 0, 0.25);
            background: rgba(255, 215, 0, 0.15);
            color: var(--color-gold);
            text-shadow: 0 0 5px rgba(255, 215, 0, 0.15);
        }
        .ticker-header {
            padding: 0 10px;
            height: 100%;
            display: flex;
            align-items: center;
            z-index: 2;
            font-size: 10px;
            font-weight: 800;
            text-transform: uppercase;
            border-radius: 5px 0 0 5px;
            flex-shrink: 0;
            position: absolute;
            left: 0;
        }
        .caution-ticker .ticker-header {
            background: rgba(255, 71, 87, 0.25);
            border-right: 1px solid rgba(255, 71, 87, 0.4);
            color: #ff4757;
        }
        .news-ticker .ticker-header {
            background: rgba(255, 215, 0, 0.25);
            border-right: 1px solid rgba(255, 215, 0, 0.4);
            color: #ffd700;
        }
        .ticker-wrap {
            display: inline-block;
            white-space: nowrap;
            padding-left: 100%;
            animation: marquee 30s linear infinite;
        }
        .news-ticker .ticker-wrap {
            animation-duration: 48s;
        }
        @keyframes marquee {
            0% { transform: translate3d(0, 0, 0); }
            100% { transform: translate3d(-100%, 0, 0); }
        }
        .ticker-item {
            display: inline-block;
            padding: 0 30px;
        }
    </style>
</head>
<body>
    
    <!-- Global JavaScript Error catching banner -->
    <script>
        window.onerror = function(message, source, lineno, colno, error) {
            var errDiv = document.createElement('div');
            errDiv.style.position = 'fixed';
            errDiv.style.top = '0';
            errDiv.style.left = '0';
            errDiv.style.width = '100%';
            errDiv.style.background = '#ff3366';
            errDiv.style.color = '#ffffff';
            errDiv.style.padding = '15px';
            errDiv.style.zIndex = '99999';
            errDiv.style.fontFamily = 'monospace';
            errDiv.style.fontSize = '12px';
            errDiv.style.boxShadow = '0 4px 15px rgba(0,0,0,0.5)';
            errDiv.style.boxSizing = 'border-box';
            errDiv.innerHTML = '<strong>❌ JAVASCRIPT ERROR:</strong> ' + message + '<br><strong>Line:</strong> ' + lineno + ' | <strong>Col:</strong> ' + colno + '<br><strong>File:</strong> ' + source;
            document.body.appendChild(errDiv);
            return false;
        };
    </script>

    <!-- ── Settings Drawer & Gear Overlay ──────────────── -->
    <div class="config-overlay" id="config-overlay" onclick="toggleConfigDrawer()"></div>
    <div class="config-drawer" id="config-drawer">
        <div class="drawer-header">
            <h3>⚙️ Configurations</h3>
            <button class="drawer-close" onclick="toggleConfigDrawer()">✕</button>
        </div>
        <div class="settings-grid">
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Trading Mode</span>
                    <span class="setting-desc">Select operational timeframe</span>
                </div>
            </div>
            <div class="mode-selector">
                <button class="mode-btn" id="btn-mode-scalping" onclick="setTradingMode('scalping')">Scalping</button>
                <button class="mode-btn" id="btn-mode-intraday" onclick="setTradingMode('intraday')">Intraday</button>
                <button class="mode-btn" id="btn-mode-swing" onclick="setTradingMode('swing')">Swing</button>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Auto Trade Mode</span>
                    <span class="setting-desc">Enable automated order execution</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-autotrade" onchange="toggleSetting('auto_trade_enabled')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Paper Mode</span>
                    <span class="setting-desc">Simulated trades vs live broker deals</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-paper" onchange="toggleSetting('paper_mode')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Compounding Sizing</span>
                    <span class="setting-desc">Size lot based on floating equity</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-compounding" onchange="toggleSetting('compounding_mode')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Hedging Allowed</span>
                    <span class="setting-desc">Concurrent Buy & Sell on symbol</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-hedging" onchange="toggleSetting('hedging_mode')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Trailing Stop</span>
                    <span class="setting-desc">Trailing profit stops</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-trailing" onchange="toggleSetting('trailing_stop_enabled')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Break-Even Auto</span>
                    <span class="setting-desc">Move SL to entry when in profit</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-breakeven" onchange="toggleSetting('break_even_enabled')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">News Sentiment Filter</span>
                    <span class="setting-desc">Block entry if high news volatility</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-news-filter" onchange="toggleSetting('news_filter_enabled')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Self-Learning Filter</span>
                    <span class="setting-desc">Filter trades on AI confidence matching</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-self-learning" onchange="toggleSetting('self_learning_filter')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row" style="margin-top:10px;">
                <div class="setting-info">
                    <span class="setting-name">Risk Percent</span>
                    <span class="setting-desc">Allocated capital risk per trade</span>
                </div>
            </div>
            <div class="range-slider-container">
                <input type="range" id="input-risk" min="0.25" max="5.0" step="0.25" value="1.0" oninput="updateRiskValue(this.value)" onchange="saveRiskSetting(this.value)">
                <span id="lbl-risk-val" style="font-weight:700;">1.0%</span>
            </div>
            <div class="setting-row" style="margin-top:10px;">
                <div class="setting-info">
                    <span class="setting-name">Max Daily Trades</span>
                    <span class="setting-desc">Limit of total trades per day</span>
                </div>
            </div>
            <div class="range-slider-container">
                <input type="range" id="input-max-daily" min="1" max="10" step="1" value="3" oninput="updateMaxDailyValue(this.value)" onchange="saveMaxDailySetting(this.value)">
                <span id="lbl-max-daily-val" style="font-weight:700;">3</span>
            </div>
            
            <!-- Connection Settings -->
            <div class="setting-row" style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 15px; display: block;">
                <div class="setting-info" style="margin-bottom: 8px;">
                    <span class="setting-name">Backend API URL</span>
                    <span class="setting-desc">Configure host & port if disconnected</span>
                </div>
                <input type="text" id="input-api-url" placeholder="http://localhost:18080" style="background: rgba(0,0,0,0.3); border: 1px solid var(--glass-border); color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 600; outline: none; width: 100%; padding: 6px 12px; border-radius: 8px; box-sizing: border-box;" onchange="saveApiUrlSetting(this.value)">
            </div>
        </div>
        <div style="flex-grow:1;"></div>
        <button class="btn-train" onclick="triggerTraining()">Trigger AI Auto-Train</button>
        <button class="btn-panic" onclick="panicCloseAll()">Panic Close All</button>
    </div>

    <!-- ── Main Dashboard Panel ─────────────────────────── -->
    <div class="main-dashboard">
        <header>
            <div class="logo-section">
                <h1 id="main-header">⚡ PULSE VIPER <span style="font-size: 12px; color: var(--color-blue); letter-spacing: 0.5px; border: 1px solid var(--color-blue); padding: 2px 8px; border-radius: 4px;">SMC EA</span></h1>
            </div>
            <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 8px; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 6px 12px; border-radius: 30px;">
                    <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">SYMBOL:</span>
                    <select id="symbol-select" onchange="changeSymbol(this.value)" style="background: transparent; border: none; color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 12px; font-weight: 700; outline: none; cursor: pointer;">
                        <option value="BTCUSDm" style="background: var(--bg-dark); color: var(--text-primary);">BTCUSDm</option>
                        <option value="XAUUSDm" style="background: var(--bg-dark); color: var(--text-primary);">XAUUSDm</option>
                        <option value="EURUSDm" style="background: var(--bg-dark); color: var(--text-primary);">EURUSDm</option>
                        <option value="GBPUSDm" style="background: var(--bg-dark); color: var(--text-primary);">GBPUSDm</option>
                        <option value="USDJPYm" style="background: var(--bg-dark); color: var(--text-primary);">USDJPYm</option>
                    </select>
                </div>
                <div style="display: flex; align-items: center; gap: 4px; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 4px 8px; border-radius: 30px;">
                    <input type="text" id="custom-symbol-input" placeholder="Add Pair (e.g. XAUUSDc)" style="background: transparent; border: none; color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 600; outline: none; width: 140px; padding: 2px 4px;">
                    <button onclick="addCustomSymbol()" style="background: var(--color-blue); border: none; color: #070a13; font-weight: bold; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1.0)'" title="Add Custom Symbol">+</button>
                </div>
                <div class="status-badge" id="spread-badge">
                    <span id="spread-lbl">SPREAD: --</span>
                </div>
                <div class="status-badge" id="latency-badge">
                    <span id="latency-lbl">LATENCY: --</span>
                </div>
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span id="broker-name">DETECTING BROKER...</span>
                </div>
                <button class="gear-btn" id="gear-toggle-btn" onclick="toggleConfigDrawer()" title="Open Configuration Panel">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                </button>
            </div>
        </header>

        <!-- Session Banner Row with UTC and Local Clocks -->
        <div class="session-banner-row" style="display: flex; align-items: center; justify-content: space-between; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 8px 16px; border-radius: 12px; margin-bottom: 12px; flex-wrap: wrap; gap: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Active Sessions:</span>
                <div id="header-sessions" style="display: flex; gap: 6px; align-items: center;">
                    <span style="color: var(--text-muted); font-size: 11px;">Loading sessions...</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 6px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px;">
                    <span style="font-size: 10px; font-weight: 700; color: var(--text-muted);">LOCAL:</span>
                    <span id="local-clock" style="font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 700; color: var(--color-blue); text-shadow: 0 0 6px rgba(59,130,246,0.3);">--:--:--</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px;">
                    <span style="font-size: 10px; font-weight: 700; color: var(--text-muted);">UTC:</span>
                    <span id="utc-clock" style="font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 700; color: var(--color-green); text-shadow: 0 0 6px rgba(16,185,129,0.3);">--:--:--</span>
                </div>
            </div>
        </div>

        <!-- Ticker Ribbons Row -->
        <div class="tickers-container">
            <div class="ticker-row caution-ticker">
                <div class="ticker-header">⚠️ WARNING</div>
                <div class="ticker-wrap" id="caution-ticker-wrap">
                    <span class="ticker-item">HIGH VOLATILITY DETECTED ON SCALPING SYMBOLS — EXERCISE CAUTION</span>
                    <span class="ticker-item">MARGIN LEVEL CRITICAL VALUE EXHAUSTION SAFETY LIMIT ACTIVE</span>
                    <span class="ticker-item">VOLUME DISASTER SAFETY SYSTEM: BYPASSED TO PREVENT EARLY WICK TRAPS</span>
                    <span class="ticker-item">COMPACT TRADE MANAGEMENT SYSTEM VERIFYING MT5 CONNECTION INTEGRITY</span>
                </div>
            </div>
            <div class="ticker-row news-ticker">
                <div class="ticker-header">📰 NEWS</div>
                <div class="ticker-wrap" id="news-ticker-wrap">
                    <span class="ticker-item" style="color: var(--text-muted);">No headlines loaded yet. Scraper starting...</span>
                </div>
            </div>
        </div>

        <!-- Main Grid Layout -->
        <div class="dashboard-container">
            <!-- COLUMN 1: SENTIMENT GAUGE & INDICATORS PANEL -->
            <div class="card" style="gap: 12px;">
                <div class="card-title">🧠 Tech Sentiment & Bias</div>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                    <div class="sentiment-dial-box">
                        <span class="dial-label">News Score</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-news" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-news">0.0</span>
                        </div>
                        <span class="dial-direction" id="dir-news">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">D1 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-d1" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-d1">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-d1">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">H4 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-h4" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-h4">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-h4">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">H1 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-h1" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-h1">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-h1">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">M30 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-m30" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-m30">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-m30">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">M15 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-m15" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-m15">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-m15">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">M5 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-m5" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-m5">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-m5">Neutral</span>
                    </div>
                    <div class="sentiment-dial-box">
                        <span class="dial-label">M1 Bias</span>
                        <div class="dial-svg-container">
                            <svg class="dial-svg" width="70" height="70" style="position: absolute; top:0; left:0; transform: rotate(180deg);">
                                <circle class="dial-bg" cx="35" cy="35" r="30"></circle>
                                <circle class="dial-progress" id="dial-m1" cx="35" cy="35" r="30" stroke="var(--color-blue)"></circle>
                            </svg>
                            <span class="dial-text" id="val-m1">0%</span>
                        </div>
                        <span class="dial-direction" id="dir-m1">Neutral</span>
                    </div>
                </div>

                <div class="bias-indicator" style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:10px; display:flex; justify-content:space-between; font-size:12px;">
                    <span class="dial-label">H1 Trend Bias</span>
                    <span id="lbl-h1-bias" style="font-weight:700;">Neutral</span>
                </div>
                <div class="bias-indicator" style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:10px; display:flex; justify-content:space-between; font-size:12px;">
                    <span class="dial-label">M15 Sweep Signal</span>
                    <span id="lbl-m15-sweep" style="font-weight:700;">Neutral</span>
                </div>
                <div class="bias-indicator" style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:10px; display:flex; justify-content:space-between; font-size:12px;">
                    <span class="dial-label">M5 Structure Shift</span>
                    <span id="lbl-m5-mss" style="font-weight:700;">Neutral</span>
                </div>
                
                <div class="bias-indicator" id="usd-forecast-card" style="background:rgba(0,168,255,0.05); border:1px solid rgba(0,168,255,0.15); padding:10px 14px; border-radius:10px; display:flex; justify-content:space-between; align-items:center; font-size:12px;">
                    <span class="dial-label" style="color:var(--color-blue); font-weight:700;">USD Forecast Bias</span>
                    <span id="lbl-usd-forecast" style="font-weight:700; padding:2px 8px; border-radius:4px; color:var(--color-blue); border:1px solid var(--color-blue); text-shadow:0 0 5px var(--glow-blue);">NEUTRAL</span>
                </div>

                <div style="font-size:13px; font-weight:600; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px; margin-top:5px;">
                    <span>📅 Upcoming Economic Events</span>
                </div>
                <div class="calendar-list" id="calendar-events-list" style="display:flex; flex-direction:column; gap:6px; max-height:180px; overflow-y:auto; margin-bottom:10px; padding-right:4px;">
                    <span style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">Loading economic calendar...</span>
                </div>

                <div style="font-size:13px; font-weight:600; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px; margin-top:5px;">
                    <span>📰 Economic Indicators Feed</span>
                </div>
                <div class="news-list" id="drawer-news-list" style="max-height:220px; overflow-y:auto;">
                    <span style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">Fetching news feed...</span>
                </div>
            </div>

            <!-- COLUMN 2: CHARTING AREA & OPEN POSITIONS -->
            <div style="display: flex; flex-direction: column; gap: 20px;">
                <div class="card">
                    <div class="chart-header">
                        <span style="font-weight: 700; font-size: 14px;" id="chart-symbol-title">📊 Candlestick Level Chart</span>
                        <div class="timeframe-selector">
                            <button class="tf-btn" id="btn-tf-m1" onclick="setTimeframe('M1')">M1</button>
                            <button class="tf-btn active" id="btn-tf-m5" onclick="setTimeframe('M5')">M5</button>
                            <button class="tf-btn" id="btn-tf-m15" onclick="setTimeframe('M15')">M15</button>
                            <button class="tf-btn" id="btn-tf-m30" onclick="setTimeframe('M30')">M30</button>
                            <button class="tf-btn" id="btn-tf-h1" onclick="setTimeframe('H1')">H1</button>
                            <button class="tf-btn" id="btn-tf-h4" onclick="setTimeframe('H4')">H4</button>
                            <button class="tf-btn" id="btn-tf-d1" onclick="setTimeframe('D1')">D1</button>
                        </div>
                        <div class="chart-tools">
                            <button class="tool-btn" id="btn-tool-support" onclick="toggleDrawingMode('support')" title="Draw custom Support level on chart">Draw Support</button>
                            <button class="tool-btn" id="btn-tool-resistance" onclick="toggleDrawingMode('resistance')" title="Draw custom Resistance level on chart">Draw Resistance</button>
                            <button class="tool-btn" onclick="clearDrawings()" title="Clear drawing lines">Clear</button>
                        </div>
                    </div>
                    <div class="chart-holder" style="background: rgba(0, 0, 0, 0.25); border-radius: 12px; border: 1px solid var(--glass-border); overflow: hidden; height: 450px; position: relative;">
                        <canvas id="canvas-chart" style="display: block; width: 100%; height: 100%; cursor: crosshair;"></canvas>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">💰 Active Positions</div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Symbol</th>
                                    <th>Action</th>
                                    <th>Volume</th>
                                    <th>Entry Price</th>
                                    <th>Stop Loss</th>
                                    <th>Take Profit</th>
                                    <th>Current PnL</th>
                                </tr>
                            </thead>
                            <tbody id="positions-body">
                                <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No open positions.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">⏱️ History & Logs</div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Symbol</th>
                                    <th>Action</th>
                                    <th>Volume</th>
                                    <th>Entry</th>
                                    <th>Close Price</th>
                                    <th>Reason</th>
                                    <th>Outcome PnL</th>
                                </tr>
                            </thead>
                            <tbody id="history-body">
                                <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No closed trades yet.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- COLUMN 3: SYSTEM PREDICTIONS & VOLUME ANALYTICS -->
            <div style="display: flex; flex-direction: column; gap: 20px;">
                <div class="card">
                    <div class="card-title">📊 Volume Analytics</div>
                    <div class="volume-stats">
                        <div class="rvol-display" style="display:flex; justify-content:space-between; align-items:center; background:rgba(0,0,0,0.15); padding:10px; border-radius:10px; border:1px solid var(--glass-border);">
                            <div style="display:flex; flex-direction:column; gap:2px;">
                                <span class="rvol-label" style="font-size:10px; color:var(--text-muted);">Relative Volume (RVOL)</span>
                                <span class="rvol-value" id="val-rvol" style="font-size:16px; font-weight:700;">1.00</span>
                            </div>
                            <span id="badge-rvol" style="font-size:8px; font-weight:800; padding:2px 6px; border-radius:4px; background:rgba(0,168,255,0.15); color:var(--color-blue); border:1px solid rgba(0,168,255,0.3);">NORMAL</span>
                        </div>
                        
                        <div class="pressure-bar-container" style="background:rgba(0,0,0,0.15); padding:10px; border-radius:10px; border:1px solid var(--glass-border); display:flex; flex-direction:column; gap:6px;">
                            <div class="pressure-labels" style="display:flex; justify-content:space-between; font-size:11px; font-weight:700;">
                                <span style="color:var(--color-green);">BUY <span id="lbl-pressure-buy">50%</span></span>
                                <span style="color:var(--color-red);">SELL <span id="lbl-pressure-sell">50%</span></span>
                            </div>
                            <div class="pressure-bar-track" style="height:6px; width:100%; background:var(--color-red); border-radius:3px; overflow:hidden; display:flex;">
                                <div class="pressure-buy" id="bar-pressure-buy" style="height:100%; width:50%; background:var(--color-green); transition:width:0.4s ease;"></div>
                            </div>
                        </div>

                        <div style="font-size:11px; font-weight:600; color:var(--text-muted); margin-top:2px;">Volume Profile POC Histogram</div>
                        <div class="vp-chart" id="vp-chart-container" style="display:flex; flex-direction:column; gap:3px; background:rgba(0,0,0,0.25); padding:8px; border-radius:10px; border:1px solid var(--glass-border);">
                            <!-- Dynamic Content -->
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">🎯 Prediction & Auditing</div>
                    <div class="prediction-box" id="pred-card">
                        <div class="pred-title" id="pred-action">HOLDING</div>
                        <div class="pred-row">
                            <span>Setup Type</span>
                            <span id="pred-type">N/A</span>
                        </div>
                        <div class="pred-row">
                            <span>Target Entry</span>
                            <span id="pred-entry">--</span>
                        </div>
                        <div class="pred-row">
                            <span>Stop Loss</span>
                            <span id="pred-sl" style="color: var(--color-red);">--</span>
                        </div>
                        <div class="pred-row">
                            <span>Take Profit</span>
                            <span id="pred-tp" style="color: var(--color-green);">--</span>
                        </div>
                        <div class="pred-row">
                            <span>Rec. Lots</span>
                            <span id="pred-lots">0.01</span>
                        </div>
                        <div class="pred-row">
                            <span>AI Confidence</span>
                            <span id="pred-confidence">—</span>
                        </div>
                        <div class="pred-row">
                            <span>Market Regime</span>
                            <span id="pred-regime">—</span>
                        </div>
                        <div class="pred-row">
                            <span>Active Sessions</span>
                            <span id="pred-sessions">—</span>
                        </div>
                        <div class="pred-row" style="flex-direction:column; align-items:flex-start; gap:6px; border-top: 1px solid rgba(255,255,255,0.05); padding-top:6px; margin-top:4px;">
                            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
                                <span>6-TF Cascade</span>
                                <span id="align-status" style="font-size:10px; font-weight:800; color:var(--text-muted);">⏳ SCANNING</span>
                            </div>
                            <div style="display:grid; grid-template-columns: repeat(6,1fr); gap:4px; width:100%; margin-top:2px;">
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">D1</div>
                                    <div id="align-d1" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">H4</div>
                                    <div id="align-h4" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">H1</div>
                                    <div id="align-htf" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">M15</div>
                                    <div id="align-ctx" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">M5</div>
                                    <div id="align-m5" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:6px; padding:5px 3px; text-align:center;">
                                    <div style="font-size:9px; color:var(--text-muted); font-weight:700;">M1</div>
                                    <div id="align-ltf" style="font-size:9px; font-weight:800; margin-top:2px; transition:color 0.3s;">—</div>
                                </div>
                            </div>
                        </div>

                        <div class="pred-row" style="flex-direction:column; align-items:flex-start; gap:4px; border-top: 1px solid rgba(255,255,255,0.05); padding-top:6px; margin-top:4px;">
                            <span>AI Training Diagnostics</span>
                            <span id="pred-train-stats" style="color:var(--color-green); font-size:10px; font-weight:700; word-break:break-all; text-align:left;">—</span>
                        </div>
                        <div class="pred-row" style="flex-direction:column; align-items:flex-start; gap:4px; border-top: 1px solid rgba(255,255,255,0.05); padding-top:6px;">
                            <span>AI Chart Analysis</span>
                            <span id="pred-patterns" style="color:var(--color-blue); font-size:10px; font-weight:700; word-break:break-all; text-align:left;">NONE</span>
                        </div>
                    </div>
                    
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted);">Execution Skip Logs</div>
                        <div style="display:grid; grid-template-columns: repeat(2,1fr); gap:6px;">
                            <div style="background:rgba(0,0,0,0.1); padding:6px; border-radius:6px; border:1px solid var(--glass-border); text-align:center;">
                                <div style="font-size:14px; font-weight:700; color:var(--color-red);" id="skip-spread">0</div>
                                <div style="font-size:9px; color:var(--text-muted);">High Spread</div>
                            </div>
                            <div style="background:rgba(0,0,0,0.1); padding:6px; border-radius:6px; border:1px solid var(--glass-border); text-align:center;">
                                <div style="font-size:14px; font-weight:700; color:var(--color-gold);" id="skip-news">0</div>
                                <div style="font-size:9px; color:var(--text-muted);">News Blocks</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">🛠️ System Diagnostics & Safety Audit</div>
                    <div style="display:flex; flex-direction:column; gap:8px; font-size:11px;">
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>MT5 Terminal Connection</span>
                            <span id="diag-mt5" style="color:var(--color-green); font-weight:700;">CONNECTED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Margin Requirement Status</span>
                            <span id="diag-margin" style="color:var(--color-green); font-weight:700;">PASSED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Account Leverage</span>
                            <span id="diag-leverage" style="color:var(--text-primary); font-weight:700;">--</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Current Margin Level</span>
                            <span id="diag-margin-level" style="color:var(--color-green); font-weight:700;">--</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Equity / Balance</span>
                            <span id="diag-equity-bal" style="color:var(--text-primary); font-weight:700;">--</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Daily Max Trade Limit</span>
                            <span id="diag-daily" style="color:var(--color-green); font-weight:700;">PASSED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Market Spread Validation</span>
                            <span id="diag-spread" style="color:var(--color-green); font-weight:700;">PASSED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>News Block Check</span>
                            <span id="diag-news" style="color:var(--color-green); font-weight:700;">PASSED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span>AI Decision Confidence</span>
                            <span id="diag-ai" style="color:var(--color-green); font-weight:700;">READY</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ── Canvas Chart JavaScript Rendering engine ────── -->
    <script>
        function getCountdownTime() {
            const now = new Date();
            let tfMinutes = 5;
            const tf = typeof activeTimeframe !== 'undefined' ? activeTimeframe : 'M5';
            if (tf === 'M1') tfMinutes = 1;
            else if (tf === 'M5') tfMinutes = 5;
            else if (tf === 'M15') tfMinutes = 15;
            else if (tf === 'M30') tfMinutes = 30;
            else if (tf === 'H1') tfMinutes = 60;
            else if (tf === 'H4') tfMinutes = 240;
            else if (tf === 'D1') tfMinutes = 1440;

            const tfSeconds = tfMinutes * 60;
            let passedSeconds = 0;

            if (tfMinutes < 60) {
                passedSeconds = (now.getMinutes() % tfMinutes) * 60 + now.getSeconds();
            } else if (tfMinutes < 1440) {
                const hours = now.getHours();
                const startHour = hours - (hours % (tfMinutes / 60));
                passedSeconds = ((hours - startHour) * 3600) + (now.getMinutes() * 60) + now.getSeconds();
            } else {
                passedSeconds = (now.getHours() * 3600) + (now.getMinutes() * 60) + now.getSeconds();
            }

            const remaining = Math.max(0, tfSeconds - passedSeconds);
            const m = Math.floor(remaining / 60);
            const s = remaining % 60;
            return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }

        function getSolidColor(colorStr) {
            if (!colorStr) return '#ffffff';
            if (colorStr.startsWith('rgba')) {
                const match = colorStr.match(/rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,/);
                if (match) {
                    return `rgb(${match[1]}, ${match[2]}, ${match[3]})`;
                }
            }
            return colorStr;
        }

        class CanvasChart {
            constructor(canvasId) {
                this.canvas = document.getElementById(canvasId);
                this.ctx = this.canvas.getContext('2d');
                this.candles = [];
                this.levels = {};
                this.trades = [];
                this.userLines = [];
                this.zoom = 10;
                this.offsetX = 0;
                this.isDragging = false;
                this.startX = 0;
                this.startY = 0;
                this.startOffset = 0;
                this.startOffsetY = 0;
                this.mouseX = null;
                this.mouseY = null;
                this.bidPrice = 0;
                this.askPrice = 0;
                this.offsetY = 0;
                this.zoomY = 1.0;
                
                this.resize();
                window.addEventListener('resize', () => this.resize());
                
                this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
                this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
                this.canvas.addEventListener('mouseup', () => this.onMouseUp());
                this.canvas.addEventListener('mouseleave', () => { this.onMouseUp(); this.mouseX = null; this.mouseY = null; this.draw(); });
                this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
                this.canvas.addEventListener('click', (e) => this.onClick(e));
            }
            
            formatPrice(price) {
                if (price === undefined || price === null || isNaN(price)) return "";
                if (price < 5) return price.toFixed(5);
                if (price < 50) return price.toFixed(4);
                if (price < 500) return price.toFixed(3);
                return price.toFixed(2);
            }
            
            drawWatermark() {
                this.ctx.save();
                this.ctx.fillStyle = 'rgba(255, 255, 255, 0.04)'; // faint premium look
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                
                const selectSymbolEl = document.getElementById('select-symbol');
                const sym = selectSymbolEl ? selectSymbolEl.value : 'XAUUSDm';
                const displaySym = sym.replace('m', '').replace('c', '').replace('.c', '').replace('t', '').toUpperCase();
                
                let watermarkText = displaySym;
                if (displaySym.length === 6) {
                    watermarkText = displaySym.substring(0, 3) + '/' + displaySym.substring(3, 6);
                }
                
                this.ctx.font = 'bold 55px Outfit, sans-serif';
                this.ctx.fillText(watermarkText, (this.width - 70) / 2, this.height / 2 - 20);
                
                this.ctx.font = 'bold 12px Outfit, sans-serif';
                let descText = 'REALTIME SMC ANALYTICS';
                if (displaySym.includes('XAU') || displaySym.includes('GOLD')) {
                    descText = 'Gold vs US Dollar';
                } else if (displaySym.includes('EURUSD')) {
                    descText = 'Euro vs US Dollar';
                } else if (displaySym.includes('GBPUSD')) {
                    descText = 'Great Britain Pound vs US Dollar';
                } else if (displaySym.includes('BTCUSD')) {
                    descText = 'Bitcoin vs US Dollar';
                }
                this.ctx.fillText(descText, (this.width - 70) / 2, this.height / 2 + 15);
                this.ctx.restore();
            }
            
            calculateEMA(period) {
                if (this.candles.length < period) return [];
                const ema = new Array(this.candles.length);
                const k = 2 / (period + 1);
                
                let sum = 0;
                for (let i = 0; i < period; i++) {
                    sum += this.candles[i].close;
                }
                let prevEma = sum / period;
                ema[period - 1] = prevEma;
                
                for (let i = period; i < this.candles.length; i++) {
                    const curEma = this.candles[i].close * k + prevEma * (1 - k);
                    ema[i] = curEma;
                    prevEma = curEma;
                }
                return ema;
            }
            
            drawEMAs(minPrice, maxPrice) {
                if (this.candles.length < 21) return;
                const ema9 = this.calculateEMA(9);
                const ema21 = this.calculateEMA(21);
                
                const candleWidth = this.zoom;
                const totalWidth = candleWidth + 2;
                const rightOffset = Math.floor(this.offsetX / totalWidth);
                const numVisible = Math.ceil(this.width / totalWidth);
                const startIndex = Math.max(0, this.candles.length - numVisible - rightOffset);
                
                // Draw EMA 21 (orange)
                this.ctx.save();
                this.ctx.strokeStyle = 'rgba(230, 126, 34, 0.65)'; // Orange line
                this.ctx.lineWidth = 1.5;
                this.ctx.beginPath();
                let started21 = false;
                for (let i = startIndex; i < this.candles.length; i++) {
                    const val = ema21[i];
                    if (val === undefined || isNaN(val)) continue;
                    const x = this.width - ((this.candles.length - i - rightOffset) * totalWidth) + this.offsetX % totalWidth + candleWidth / 2;
                    const y = this.priceToPixelY(val, minPrice, maxPrice);
                    if (y >= 0 && y <= this.height - 25) {
                        if (!started21) {
                            this.ctx.moveTo(x, y);
                            started21 = true;
                        } else {
                            this.ctx.lineTo(x, y);
                        }
                    }
                }
                this.ctx.stroke();
                this.ctx.restore();
                
                // Draw EMA 9 (green)
                this.ctx.save();
                this.ctx.strokeStyle = 'rgba(46, 204, 113, 0.65)'; // Green line
                this.ctx.lineWidth = 1.5;
                this.ctx.beginPath();
                let started9 = false;
                for (let i = startIndex; i < this.candles.length; i++) {
                    const val = ema9[i];
                    if (val === undefined || isNaN(val)) continue;
                    const x = this.width - ((this.candles.length - i - rightOffset) * totalWidth) + this.offsetX % totalWidth + candleWidth / 2;
                    const y = this.priceToPixelY(val, minPrice, maxPrice);
                    if (y >= 0 && y <= this.height - 25) {
                        if (!started9) {
                            this.ctx.moveTo(x, y);
                            started9 = true;
                        } else {
                            this.ctx.lineTo(x, y);
                        }
                    }
                }
                this.ctx.stroke();
                this.ctx.restore();
            }
            
            resize() {
                const rect = this.canvas.parentElement.getBoundingClientRect();
                const newWidth = Math.floor(rect.width);
                const newHeight = 450;
                
                // Only resize if logical dimensions have actually changed to prevent infinite layout feedback loops
                if (this.width === newWidth && this.height === newHeight) {
                    return;
                }
                
                const dpr = window.devicePixelRatio || 1;
                this.width = newWidth;
                this.height = newHeight;
                this.canvas.width = this.width * dpr;
                this.canvas.height = this.height * dpr;
                this.canvas.style.width = this.width + 'px';
                this.canvas.style.height = this.height + 'px';
                this.ctx.resetTransform();
                this.ctx.scale(dpr, dpr);
                this.draw();
            }
            
            setData(candles, levels, trades) {
                this.candles = candles;
                this.levels = levels;
                this.trades = trades;
                this.draw();
            }
            
            onMouseDown(e) {
                if (chartDrawingMode) return;
                this.isDragging = true;
                this.startX = e.clientX;
                this.startY = e.clientY;
                this.startOffset = this.offsetX;
                this.startOffsetY = this.offsetY;
            }
            
            onMouseMove(e) {
                const rect = this.canvas.getBoundingClientRect();
                this.mouseX = e.clientX - rect.left;
                this.mouseY = e.clientY - rect.top;
                
                if (this.isDragging) {
                    const dx = e.clientX - this.startX;
                    const dy = e.clientY - this.startY;
                    this.offsetX = this.startOffset + dx;
                    this.offsetY = this.startOffsetY + dy;
                }
                this.draw();
            }
            
            onMouseUp() {
                this.isDragging = false;
            }
            
            onWheel(e) {
                e.preventDefault();
                if (e.shiftKey) {
                    if (e.deltaY < 0) {
                        this.zoomY = Math.min(this.zoomY + 0.1, 5.0);
                    } else {
                        this.zoomY = Math.max(this.zoomY - 0.1, 0.2);
                    }
                } else {
                    if (e.deltaY < 0) {
                        this.zoom = Math.min(this.zoom + 1, 30);
                    } else {
                        this.zoom = Math.max(this.zoom - 1, 3);
                    }
                }
                this.draw();
            }
            
            onClick(e) {
                if (!chartDrawingMode) return;
                const rect = this.canvas.getBoundingClientRect();
                const mouseY = e.clientY - rect.top;
                const price = this.pixelToPriceY(mouseY);
                
                let color = '#00a8ff';
                let title = 'USER LINE';
                if (chartDrawingMode === 'support') {
                    color = '#00f076';
                    title = 'SUPPORT';
                } else if (chartDrawingMode === 'resistance') {
                    color = '#ff3366';
                    title = 'RESISTANCE';
                }
                
                this.userLines.push({ price, type: chartDrawingMode, color, title });
                toggleDrawingMode(null);
                this.draw();
            }
            
            clearDrawings() {
                this.userLines = [];
                this.draw();
            }
            
            pixelToPriceY(y) {
                const { minPrice, maxPrice } = this.getPriceRange();
                const height = this.height - 65;
                const pct = 1 - (y - 20 - (this.offsetY || 0)) / height;
                return minPrice + pct * (maxPrice - minPrice);
            }
            
            priceToPixelY(price, minPrice, maxPrice) {
                const height = this.height - 65;
                const range = maxPrice - minPrice || 1;
                const pct = (price - minPrice) / range;
                return this.height - 45 - pct * height + (this.offsetY || 0);
            }
            
            candleIndexFromX(x) {
                if (this.candles.length === 0) return null;
                const candleWidth = this.zoom;
                const totalWidth = candleWidth + 2;
                const rightOffset = Math.floor(this.offsetX / totalWidth);
                const val = (this.width - x + (this.offsetX % totalWidth)) / totalWidth;
                const index = Math.round(this.candles.length - rightOffset - val);
                if (index >= 0 && index < this.candles.length) {
                    return index;
                }
                return null;
            }
            
            getPriceRange() {
                if (this.candles.length === 0) return { minPrice: 0, maxPrice: 100 };
                const visible = this.getVisibleCandles();
                let minPrice = Infinity;
                let maxPrice = -Infinity;
                visible.forEach(c => {
                    if (c.low < minPrice) minPrice = c.low;
                    if (c.high > maxPrice) maxPrice = c.high;
                });
                
                const candleCenter = (maxPrice + minPrice) / 2;
                const candleRange = maxPrice - minPrice;
                const maxDev = Math.max(candleRange * 1.5, candleCenter * 0.02);

                if (this.trades && this.trades.length > 0) {
                    this.trades.forEach(t => {
                        if (t.entry && t.entry > 0 && Math.abs(t.entry - candleCenter) < maxDev) {
                            if (t.entry < minPrice) minPrice = t.entry;
                            if (t.entry > maxPrice) maxPrice = t.entry;
                        }
                        if (t.sl && t.sl > 0 && Math.abs(t.sl - candleCenter) < maxDev) {
                            if (t.sl < minPrice) minPrice = t.sl;
                            if (t.sl > maxPrice) maxPrice = t.sl;
                        }
                        if (t.tp && t.tp > 0 && Math.abs(t.tp - candleCenter) < maxDev) {
                            if (t.tp < minPrice) minPrice = t.tp;
                            if (t.tp > maxPrice) maxPrice = t.tp;
                        }
                    });
                }

                if (this.levels) {
                    if (this.levels.support && this.levels.support > 0 && Math.abs(this.levels.support - candleCenter) < maxDev) {
                        if (this.levels.support < minPrice) minPrice = this.levels.support;
                    }
                    if (this.levels.resistance && this.levels.resistance > 0 && Math.abs(this.levels.resistance - candleCenter) < maxDev) {
                        if (this.levels.resistance > maxPrice) maxPrice = this.levels.resistance;
                    }
                    if (this.levels.poc && this.levels.poc > 0 && Math.abs(this.levels.poc - candleCenter) < maxDev) {
                        if (this.levels.poc < minPrice) minPrice = this.levels.poc;
                        if (this.levels.poc > maxPrice) maxPrice = this.levels.poc;
                    }
                }

                const currentBid = this.bidPrice || (this.candles.length > 0 ? this.candles[this.candles.length - 1].close : 0);
                if (currentBid && Math.abs(currentBid - candleCenter) < maxDev) {
                    if (currentBid < minPrice) minPrice = currentBid;
                    if (currentBid > maxPrice) maxPrice = currentBid;
                }
                if (this.askPrice && Math.abs(this.askPrice - candleCenter) < maxDev) {
                    if (this.askPrice < minPrice) minPrice = this.askPrice;
                    if (this.askPrice > maxPrice) maxPrice = this.askPrice;
                }

                const range = maxPrice - minPrice;
                const pad = range * 0.1 || 1;
                
                const zoomFactor = this.zoomY || 1.0;
                const centerPrice = (maxPrice + minPrice) / 2;
                const newHalfRange = (range / 2) / zoomFactor;
                
                return { 
                    minPrice: centerPrice - newHalfRange - pad, 
                    maxPrice: centerPrice + newHalfRange + pad 
                };
            }
            
            getVisibleCandles() {
                const step = this.zoom + 2;
                const visibleCount = Math.ceil(this.width / step);
                const rightOffset = Math.floor(this.offsetX / step);
                const start = Math.max(0, this.candles.length - visibleCount - rightOffset);
                const end = Math.min(this.candles.length, this.candles.length - rightOffset);
                return this.candles.slice(start, end);
            }
            
            draw() {
                try {
                    // Bulletproof physical clear for high-DPI scaled canvas
                    this.ctx.save();
                    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
                    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                    this.ctx.restore();

                    if (this.candles.length === 0) {
                        this.ctx.fillStyle = '#8b9bb4';
                        this.ctx.font = '14px Outfit';
                        this.ctx.textAlign = 'center';
                        this.ctx.fillText('No candle data available', this.width / 2, this.height / 2);
                        return;
                    }
                    
                    const { minPrice, maxPrice } = this.getPriceRange();
                    
                    // Draw watermark in background
                    this.drawWatermark();
                    const candleWidth = this.zoom;
                    const totalWidth = candleWidth + 2;
                    
                    const numVisible = Math.ceil(this.width / totalWidth);
                    const rightOffset = Math.floor(this.offsetX / totalWidth);
                    const startIndex = Math.max(0, this.candles.length - numVisible - rightOffset);
                    
                    // Draw grid lines
                    this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
                    this.ctx.lineWidth = 1;
                    for (let i = 0; i < this.width - 70; i += 50) {
                        this.ctx.beginPath(); this.ctx.moveTo(i, 0); this.ctx.lineTo(i, this.height - 25); this.ctx.stroke();
                    }
                    for (let j = 0; j < this.height - 25; j += 40) {
                        this.ctx.beginPath(); this.ctx.moveTo(0, j); this.ctx.lineTo(this.width - 70, j); this.ctx.stroke();
                    }
                    // Draw CRT and OB zones in the background
                    if (this.levels) {
                        const drawWidth = this.width - 70;
                        
                        // 1. CRT Zone Shaded Box
                        if (this.levels.crt_high && this.levels.crt_low) {
                            const crtHighY = this.priceToPixelY(this.levels.crt_high, minPrice, maxPrice);
                            const crtLowY = this.priceToPixelY(this.levels.crt_low, minPrice, maxPrice);
                            this.ctx.save();
                            this.ctx.fillStyle = 'rgba(168, 85, 247, 0.08)'; // Glassy purple
                            this.ctx.strokeStyle = 'rgba(168, 85, 247, 0.35)'; // Dotted purple border
                            this.ctx.lineWidth = 1;
                            this.ctx.setLineDash([4, 4]);
                            const yStart = Math.min(crtHighY, crtLowY);
                            const height = Math.abs(crtHighY - crtLowY);
                            this.ctx.fillRect(0, yStart, drawWidth, height);
                            this.ctx.strokeRect(0, yStart, drawWidth, height);
                            this.ctx.restore();
                        }
                        
                        // 2. Order Block Zone Shaded Box
                        if (this.levels.ob_top && this.levels.ob_bottom) {
                            const obTopY = this.priceToPixelY(this.levels.ob_top, minPrice, maxPrice);
                            const obBottomY = this.priceToPixelY(this.levels.ob_bottom, minPrice, maxPrice);
                            const isBullish = this.levels.ob_direction === 'bullish';
                            this.ctx.save();
                            // Greenish for bullish OB, Reddish for bearish OB
                            this.ctx.fillStyle = isBullish ? 'rgba(0, 240, 118, 0.06)' : 'rgba(255, 51, 102, 0.06)';
                            this.ctx.strokeStyle = isBullish ? 'rgba(0, 240, 118, 0.25)' : 'rgba(255, 51, 102, 0.25)';
                            this.ctx.lineWidth = 1;
                            this.ctx.setLineDash([4, 4]);
                            const yStart = Math.min(obTopY, obBottomY);
                            const height = Math.abs(obTopY - obBottomY);
                            this.ctx.fillRect(0, yStart, drawWidth, height);
                            this.ctx.strokeRect(0, yStart, drawWidth, height);
                            this.ctx.restore();
                        }
                    }
                    
                    // Draw candles
                    for (let i = startIndex; i < this.candles.length; i++) {
                        const candle = this.candles[i];
                        const x = this.width - ((this.candles.length - i - rightOffset) * totalWidth) + this.offsetX % totalWidth;
                        
                        if (x < -candleWidth || x > this.width + candleWidth) continue;
                        
                        const openY = this.priceToPixelY(candle.open, minPrice, maxPrice);
                        const closeY = this.priceToPixelY(candle.close, minPrice, maxPrice);
                        const highY = this.priceToPixelY(candle.high, minPrice, maxPrice);
                        const lowY = this.priceToPixelY(candle.low, minPrice, maxPrice);
                        
                        const range = candle.high - candle.low;
                        const buy_pressure = range > 0 ? (candle.close - candle.low) / range : 0.5;
                        
                        let color = '#ff3366';
                        if (candle.close >= candle.open) color = '#00f076';
                        
                        // Neon pressure colors
                        if (buy_pressure >= 0.60) {
                            color = '#00f0ff';
                        } else if (buy_pressure <= 0.40) {
                            color = '#ff007f';
                        }
                        
                        this.ctx.strokeStyle = color;
                        this.ctx.fillStyle = color;
                        this.ctx.lineWidth = 1.5;
                        
                        this.ctx.beginPath();
                        this.ctx.moveTo(x + candleWidth / 2, highY);
                        this.ctx.lineTo(x + candleWidth / 2, lowY);
                        this.ctx.stroke();
                        
                        const bodyH = Math.max(1.5, Math.abs(closeY - openY));
                        const bodyY = Math.min(openY, closeY);
                        this.ctx.fillRect(x, bodyY, candleWidth, bodyH);
                    }
                    
                    // Draw EMAs on top of candles
                    this.drawEMAs(minPrice, maxPrice);
                    
                    // 1. Draw solid background bars for axes BEFORE indicators & price tags
                    this.drawPriceAxisBackground();
                    this.drawTimeAxisBackground();
                    
                    // 2. Draw price ticks on top of backgrounds
                    this.drawPriceAxisTicks(minPrice, maxPrice);
                    this.drawTimeAxisTicks();
                    
                    // 3. Draw indicator lines, active trades, user lines, and bid/ask (their tags will draw on top of ticks/axes cleanly)
                    if (this.levels) {
                        if (this.levels.support) this.drawHorizontalLine(this.levels.support, 'rgba(0, 240, 118, 0.75)', 'SMC SUP', minPrice, maxPrice, true);
                        if (this.levels.resistance) this.drawHorizontalLine(this.levels.resistance, 'rgba(255, 51, 102, 0.75)', 'SMC RES', minPrice, maxPrice, true);
                        if (this.levels.poc) this.drawHorizontalLine(this.levels.poc, 'rgba(255, 204, 0, 0.75)', 'POC', minPrice, maxPrice, true);
                        if (this.levels.pdh) this.drawHorizontalLine(this.levels.pdh, 'rgba(241, 245, 249, 0.8)', 'PDH', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pdl) this.drawHorizontalLine(this.levels.pdl, 'rgba(241, 245, 249, 0.8)', 'PDL', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pwh) this.drawHorizontalLine(this.levels.pwh, 'rgba(216, 180, 254, 0.8)', 'PWH', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pwl) this.drawHorizontalLine(this.levels.pwl, 'rgba(216, 180, 254, 0.8)', 'PWL', minPrice, maxPrice, false, 1, [3, 3]);
                    }
                    
                    if (this.trades) {
                        this.trades.forEach(t => {
                            const entryY = this.priceToPixelY(t.entry, minPrice, maxPrice);
                            const slY = t.sl ? this.priceToPixelY(t.sl, minPrice, maxPrice) : null;
                            const tpY = t.tp ? this.priceToPixelY(t.tp, minPrice, maxPrice) : null;
                            
                            const drawWidth = this.width - 70;
                            
                            // Draw transparent position visual zones (like TradingView's position tools)
                            if (tpY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = t.action === 'BUY' ? 'rgba(46, 204, 113, 0.12)' : 'rgba(231, 76, 60, 0.12)';
                                const yStart = Math.min(entryY, tpY);
                                const height = Math.abs(entryY - tpY);
                                this.ctx.fillRect(0, yStart, drawWidth, height);
                                this.ctx.restore();
                            }
                            
                            if (slY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = t.action === 'BUY' ? 'rgba(231, 76, 60, 0.12)' : 'rgba(46, 204, 113, 0.12)';
                                const yStart = Math.min(entryY, slY);
                                const height = Math.abs(entryY - slY);
                                this.ctx.fillRect(0, yStart, drawWidth, height);
                                this.ctx.restore();
                            }
                            
                            if (t.entry) this.drawHorizontalLine(t.entry, '#00a8ff', `${t.action} ENTRY`, minPrice, maxPrice, false, 2, [5, 5]);
                            if (t.sl) this.drawHorizontalLine(t.sl, '#ff3366', 'STOP LOSS', minPrice, maxPrice, false, 2, [5, 5]);
                            if (t.tp) this.drawHorizontalLine(t.tp, '#00f076', 'TAKE PROFIT', minPrice, maxPrice, false, 2, [5, 5]);
                        });
                    }
                    
                    this.userLines.forEach(line => {
                        this.drawHorizontalLine(line.price, line.color, line.title, minPrice, maxPrice, false, 2);
                    });
                    
                    // Draw live Bid/Ask tracking lines
                    const currentBid = this.bidPrice || (this.candles.length > 0 ? this.candles[this.candles.length - 1].close : 0);
                    const currentAsk = this.askPrice || currentBid;
                    if (currentBid) {
                        this.drawHorizontalLine(currentBid, 'rgba(255, 165, 0, 0.85)', 'BID', minPrice, maxPrice, false, 1.5, [3, 3]);
                    }
                    if (currentAsk) {
                        this.drawHorizontalLine(currentAsk, 'rgba(0, 210, 211, 0.85)', 'ASK', minPrice, maxPrice, false, 1.5, [3, 3]);
                    }
                    
                    // 4. Draw crosshair tracking lines and price axis tooltip last
                    if (this.mouseX !== null && this.mouseY !== null && this.mouseX >= 0 && this.mouseX < this.width - 70 && this.mouseY >= 0 && this.mouseY < this.height) {
                        this.ctx.save();
                        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
                        this.ctx.lineWidth = 1;
                        this.ctx.setLineDash([4, 4]);
                        
                        // Horizontal crosshair line
                        this.ctx.beginPath();
                        this.ctx.moveTo(0, this.mouseY);
                        this.ctx.lineTo(this.width - 70, this.mouseY);
                        this.ctx.stroke();
                        
                        // Vertical crosshair line
                        this.ctx.beginPath();
                        this.ctx.moveTo(this.mouseX, 0);
                        this.ctx.lineTo(this.mouseX, this.height);
                        this.ctx.stroke();
                        this.ctx.restore();
                        
                        // Price tag overlay on right axis
                        const price = this.pixelToPriceY(this.mouseY);
                        this.ctx.fillStyle = '#00a8ff';
                        this.ctx.fillRect(this.width - 70, this.mouseY - 9, 70, 18);
                        this.ctx.fillStyle = '#070a13';
                        this.ctx.font = '9px monospace';
                        this.ctx.textAlign = 'center';
                        this.ctx.fillText(this.formatPrice(price), this.width - 35, this.mouseY + 3);
                        
                        // Time tag overlay on bottom axis
                        const idx = this.candleIndexFromX(this.mouseX);
                        if (idx !== null) {
                            const candle = this.candles[idx];
                            let timeVal = candle.time || candle.date || "";
                            let timeStr = "";
                            if (timeVal) {
                                if (typeof timeVal === 'number') {
                                    const date = new Date(timeVal * 1000);
                                    const hours = date.getHours().toString().padStart(2, '0');
                                    const minutes = date.getMinutes().toString().padStart(2, '0');
                                    timeStr = `${hours}:${minutes}`;
                                } else {
                                    timeStr = String(timeVal);
                                }
                            }
                            if (timeStr) {
                                this.ctx.save();
                                this.ctx.fillStyle = 'rgba(0, 210, 211, 0.85)'; // cyan
                                this.ctx.font = '9px monospace';
                                const textWidth = this.ctx.measureText(timeStr).width + 10;
                                const rectX = Math.max(0, Math.min(this.width - 70 - textWidth, this.mouseX - textWidth/2));
                                this.ctx.fillRect(rectX, this.height - 21, textWidth, 16);
                                this.ctx.fillStyle = '#070a13';
                                this.ctx.textAlign = 'center';
                                this.ctx.fillText(timeStr, rectX + textWidth/2, this.height - 9);
                                this.ctx.restore();
                            }
                        }
                    }
                } catch (err) {
                    // Draw error message on canvas
                    this.ctx.save();
                    this.ctx.fillStyle = '#ff3366';
                    this.ctx.font = 'bold 12px monospace';
                    this.ctx.textAlign = 'left';
                    this.ctx.fillText('❌ CHART DRAW ERROR: ' + err.message, 10, 20);
                    this.ctx.fillText('Stack: ' + err.stack.split('\\n')[0], 10, 35);
                    this.ctx.restore();
                    console.error("CanvasChart draw crash:", err);
                }
            }
            
            drawHorizontalLine(price, color, label, minPrice, maxPrice, isSolid = true, lineWidth = 1, dashPattern = null) {
                const y = this.priceToPixelY(price, minPrice, maxPrice);
                if (y < 0 || y > this.height - 25) return;
                
                const solidColor = getSolidColor(color);
                
                this.ctx.save();
                this.ctx.strokeStyle = color;
                this.ctx.lineWidth = lineWidth;
                if (!isSolid && dashPattern) this.ctx.setLineDash(dashPattern);
                
                // Apply a gorgeous premium neon glow effect
                this.ctx.shadowBlur = 8;
                this.ctx.shadowColor = solidColor;
                
                this.ctx.beginPath();
                this.ctx.moveTo(0, y);
                this.ctx.lineTo(this.width - 70, y);
                this.ctx.stroke();
                this.ctx.restore();
                
                // Draw label above line
                this.ctx.fillStyle = solidColor;
                this.ctx.font = 'bold 10px Outfit';
                this.ctx.textAlign = 'left';
                this.ctx.fillText(`${label}`, 10, y - 4);
 
                // Draw price tag on the right axis
                this.ctx.save();
                this.ctx.fillStyle = solidColor;
                this.ctx.fillRect(this.width - 70, y - 8, 70, 16);
                
                this.ctx.fillStyle = '#070a13';
                this.ctx.font = 'bold 9px monospace';
                this.ctx.textAlign = 'center';
                this.ctx.fillText(this.formatPrice(price), this.width - 35, y + 3);
                this.ctx.restore();
 
                // Draw countdown badge to the left of the right axis tag if BID line
                if (label.startsWith('BID')) {
                    const countdownStr = getCountdownTime();
                    this.ctx.save();
                    this.ctx.fillStyle = 'rgba(255, 71, 87, 0.2)';
                    this.ctx.strokeStyle = '#ff4757';
                    this.ctx.lineWidth = 1;
                    
                    const badgeWidth = 42;
                    const badgeX = this.width - 70 - badgeWidth - 4;
                    const badgeY = y - 8;
                    const badgeHeight = 16;
                    
                    this.ctx.fillRect(badgeX, badgeY, badgeWidth, badgeHeight);
                    this.ctx.strokeRect(badgeX, badgeY, badgeWidth, badgeHeight);
                    
                    this.ctx.fillStyle = '#ff4757';
                    this.ctx.font = 'bold 9px monospace';
                    this.ctx.textAlign = 'center';
                    this.ctx.fillText(countdownStr, badgeX + badgeWidth/2, y + 3);
                    this.ctx.restore();
                }
            }
            
            drawPriceAxisBackground() {
                const w = this.width;
                const rightOffset = w - 70;
                this.ctx.fillStyle = '#070a13';
                this.ctx.fillRect(rightOffset, 0, 70, this.height - 25);
                this.ctx.strokeStyle = 'var(--glass-border)';
                this.ctx.lineWidth = 1;
                this.ctx.beginPath(); this.ctx.moveTo(rightOffset, 0); this.ctx.lineTo(rightOffset, this.height - 25); this.ctx.stroke();
            }

            drawPriceAxisTicks(minPrice, maxPrice) {
                const w = this.width;
                this.ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
                this.ctx.font = 'bold 9px monospace';
                this.ctx.textAlign = 'right';
                
                const numTicks = 6;
                for (let i = 0; i < numTicks; i++) {
                    const y = 30 + (i * (this.height - 85)) / (numTicks - 1);
                    const price = this.pixelToPriceY(y);
                    this.ctx.fillText(this.formatPrice(price), w - 5, y + 3);
                }
            }
 
            drawTimeAxisBackground() {
                const w = this.width;
                const h = this.height;
                const bottomOffset = h - 25;
                this.ctx.fillStyle = '#070a13';
                this.ctx.fillRect(0, bottomOffset, w, 25);
                this.ctx.strokeStyle = 'var(--glass-border)';
                this.ctx.lineWidth = 1;
                this.ctx.beginPath(); this.ctx.moveTo(0, bottomOffset); this.ctx.lineTo(w, bottomOffset); this.ctx.stroke();
            }

            drawTimeAxisTicks() {
                const w = this.width;
                const h = this.height;
                const bottomOffset = h - 25;
                if (this.candles.length === 0) return;
                
                const candleWidth = this.zoom;
                const totalWidth = candleWidth + 2;
                const rightOffset = Math.floor(this.offsetX / totalWidth);
                
                this.ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
                this.ctx.font = 'bold 9px monospace';
                this.ctx.textAlign = 'center';
                this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
                
                const step = 10;
                for (let i = 0; i < this.candles.length; i += step) {
                    const candle = this.candles[i];
                    const x = this.width - ((this.candles.length - i - rightOffset) * totalWidth) + this.offsetX % totalWidth;
                    
                    if (x > 30 && x < this.width - 75) {
                        let timeStr = "";
                        if (candle.time) {
                            if (typeof candle.time === 'number') {
                                const date = new Date(candle.time * 1000);
                                const hours = date.getHours().toString().padStart(2, '0');
                                const minutes = date.getMinutes().toString().padStart(2, '0');
                                timeStr = `${hours}:${minutes}`;
                            } else if (typeof candle.time === 'string') {
                                const parts = candle.time.split(' ');
                                timeStr = parts.length > 1 ? parts[1].substring(0, 5) : candle.time.substring(11, 16);
                            }
                        } else if (candle.date) {
                            const parts = candle.date.split(' ');
                            timeStr = parts.length > 1 ? parts[1].substring(0, 5) : candle.date.substring(11, 16);
                        }
                        if (timeStr) {
                            this.ctx.fillText(timeStr, x, h - 8);
                            this.ctx.beginPath();
                            this.ctx.moveTo(x, bottomOffset);
                            this.ctx.lineTo(x, bottomOffset + 4);
                            this.ctx.stroke();
                        }
                    }
                }
            }
        }

        let canvasChart = null;
        let activeTimeframe = 'M5';
        let chartDrawingMode = null;

        // Auto-detect and configure backend API base URL (with safe localStorage fallback)
        let apiBase = '';
        try {
            apiBase = localStorage.getItem('pulse_viper_api_url') || '';
        } catch (e) {
            console.warn("localStorage access blocked:", e);
        }

        if (!apiBase) {
            if (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '18080' && window.location.port !== '8000')) {
                apiBase = 'http://localhost:18080';
            } else {
                apiBase = window.location.origin;
            }
        }

        function initDashboard() {
            canvasChart = new CanvasChart('canvas-chart');
            
            // Populate the URL setting input in UI if it exists
            const apiInput = document.getElementById('input-api-url');
            if (apiInput) {
                apiInput.value = apiBase;
            }

            function updateClocks() {
                const now = new Date();
                const pad = (n) => String(n).padStart(2, '0');
                
                // Local clock
                const localStr = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
                const localEl = document.getElementById('local-clock');
                if (localEl) localEl.innerText = localStr;
                
                // UTC clock
                const utcStr = pad(now.getUTCHours()) + ':' + pad(now.getUTCMinutes()) + ':' + pad(now.getUTCSeconds());
                const utcEl = document.getElementById('utc-clock');
                if (utcEl) utcEl.innerText = utcStr;
            }
            updateClocks();
            setInterval(updateClocks, 1000);

            fetchChartData();
            setInterval(fetchStatus, 1500);
            setInterval(fetchChartData, 5000);
            setInterval(() => {
                if (canvasChart) {
                    canvasChart.draw();
                }
            }, 1000);
            fetchStatus();
        }

        // Bulletproof initialization: execute immediately if document is already loaded
        if (document.readyState === 'loading') {
            window.addEventListener('DOMContentLoaded', initDashboard);
        } else {
            initDashboard();
        }

        function saveApiUrlSetting(value) {
            value = value.trim();
            if (value.endsWith('/')) {
                value = value.slice(0, -1);
            }
            try {
                localStorage.setItem('pulse_viper_api_url', value);
            } catch (e) {
                console.warn("localStorage write blocked:", e);
            }
            apiBase = value;
            fetchStatus();
            fetchChartData();
        }

        async function fetchChartData() {
            try {
                const symbol = document.getElementById('symbol-select').value;
                const response = await fetch(`${apiBase}/api/chart?symbol=${symbol}&timeframe=${activeTimeframe}&_=${Date.now()}`);
                if (!response.ok) return;
                const data = await response.json();
                
                if (data.candles) {
                    canvasChart.setData(data.candles, data.levels, data.trades);
                    document.getElementById('chart-symbol-title').innerText = `📊 ${data.symbol} ${data.timeframe} Candlestick Chart (Volume pressure Colored)`;
                }
            } catch (e) {
                console.error("Failed to load chart data", e);
            }
        }

        function setTimeframe(tf) {
            activeTimeframe = tf;
            document.querySelectorAll('.tf-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`btn-tf-${tf.toLowerCase()}`).classList.add('active');
            fetchChartData();
        }

        function toggleDrawingMode(mode) {
            chartDrawingMode = mode;
            document.querySelectorAll('.tool-btn').forEach(btn => btn.classList.remove('active'));
            if (mode) {
                document.getElementById(`btn-tool-${mode}`).classList.add('active');
            }
        }

        function clearDrawings() {
            canvasChart.clearDrawings();
        }

        function toggleConfigDrawer() {
            const drawer = document.getElementById('config-drawer');
            const overlay = document.getElementById('config-overlay');
            if (drawer.classList.contains('open')) {
                drawer.classList.remove('open');
                overlay.style.display = 'none';
            } else {
                drawer.classList.add('open');
                overlay.style.display = 'block';
            }
        }

        async function changeSymbol(val) {
            sendSettingUpdate({ "active_symbol": val });
        }

        async function addCustomSymbol() {
            const input = document.getElementById('custom-symbol-input');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) return;
            
            try {
                const btn = document.querySelector('[onclick="addCustomSymbol()"]');
                const origText = btn.innerText;
                btn.innerText = '⌛';
                btn.disabled = true;
                const response = await fetch(`${apiBase}/api/add_symbol`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol })
                });
                
                const resData = await response.json();
                if (response.ok && resData.status === 'success') {
                    input.value = '';
                    fetchStatus();
                    setTimeout(() => {
                        const selectEl = document.getElementById('symbol-select');
                        selectEl.value = resData.symbol;
                        fetchChartData();
                    }, 500);
                } else {
                    alert(resData.error || 'Failed to add symbol');
                }
            } catch (err) {
                console.error("Error adding symbol", err);
                alert("Error adding symbol: " + err.message);
            } finally {
                const btn = document.querySelector('[onclick="addCustomSymbol()"]');
                btn.innerText = '+';
                btn.disabled = false;
            }
        }

        async function fetchStatus() {
            try {
                const response = await fetch(`${apiBase}/api/status?_=${Date.now()}`);
                if (!response.ok) {
                    throw new Error("HTTP error " + response.status);
                }
                const data = await response.json();
                const settings = data.settings || {};

                document.getElementById('broker-name').innerText = `${data.account.broker.toUpperCase()} (${data.account.mode.toUpperCase()})`;
                document.getElementById('latency-lbl').innerText = `LATENCY: ${data.latency_ms} ms`;

                if (data.spread && data.spread.current !== null) {
                    document.getElementById('spread-lbl').innerText = `SPREAD: ${data.spread.current} PTS (MAX: ${data.spread.max_limit})`;
                    const badge = document.getElementById('spread-badge');
                    if (data.spread.exceeded) {
                        badge.style.borderColor = 'var(--color-red)';
                        badge.style.color = 'var(--color-red)';
                    } else {
                        badge.style.borderColor = 'var(--glass-border)';
                        badge.style.color = 'var(--text-primary)';
                    }
                }

                // Update symbol selector
                if (data.symbols && data.symbols.length > 0) {
                    const selectEl = document.getElementById('symbol-select');
                    const currentValue = settings.active_symbol || selectEl.value;
                    
                    let needsRebuild = false;
                    if (selectEl.options.length !== data.symbols.length) {
                        needsRebuild = true;
                    } else {
                        for (let i = 0; i < selectEl.options.length; i++) {
                            if (selectEl.options[i].value !== data.symbols[i]) {
                                needsRebuild = true;
                                break;
                            }
                        }
                    }
                    
                    if (needsRebuild) {
                        selectEl.innerHTML = '';
                        data.symbols.forEach(sym => {
                            const opt = document.createElement('option');
                            opt.value = sym;
                            opt.text = sym;
                            opt.style.background = 'var(--bg-dark)';
                            opt.style.color = 'var(--text-primary)';
                            selectEl.appendChild(opt);
                        });
                    }
                    selectEl.value = currentValue;
                } else if (settings.active_symbol) {
                    document.getElementById('symbol-select').value = settings.active_symbol;
                }

                // Dials
                updateDial('dial-news', 'val-news', data.sentiment.news, true);
                updateDial('dial-d1', 'val-d1', data.sentiment.d1);
                updateDial('dial-h4', 'val-h4', data.sentiment.h4);
                updateDial('dial-h1', 'val-h1', data.sentiment.h1);
                updateDial('dial-m30', 'val-m30', data.sentiment.m30);
                updateDial('dial-m15', 'val-m15', data.sentiment.m15);
                updateDial('dial-m5', 'val-m5', data.sentiment.m5);
                updateDial('dial-m1', 'val-m1', data.sentiment.m1);

                // Bias text
                document.getElementById('lbl-h1-bias').innerText = data.sentiment.h1_bias_label || 'Neutral';
                document.getElementById('lbl-m15-sweep').innerText = data.sentiment.m15_sweep_label || 'Neutral';
                document.getElementById('lbl-m5-mss').innerText = data.sentiment.m5_mss_label || 'Neutral';

                // USD Forecast Bias
                const usdForecast = data.sentiment.usd_forecast_bias || 'NEUTRAL';
                const usdForecastEl = document.getElementById('lbl-usd-forecast');
                usdForecastEl.innerText = usdForecast;
                if (usdForecast === 'BULLISH') {
                    usdForecastEl.style.color = 'var(--color-green)';
                    usdForecastEl.style.borderColor = 'var(--color-green)';
                    usdForecastEl.style.textShadow = '0 0 8px var(--glow-green)';
                } else if (usdForecast === 'BEARISH') {
                    usdForecastEl.style.color = 'var(--color-red)';
                    usdForecastEl.style.borderColor = 'var(--color-red)';
                    usdForecastEl.style.textShadow = '0 0 8px var(--glow-red)';
                } else {
                    usdForecastEl.style.color = 'var(--color-blue)';
                    usdForecastEl.style.borderColor = 'var(--color-blue)';
                    usdForecastEl.style.textShadow = '0 0 8px var(--glow-blue)';
                }

                // News
                updateNewsDrawer(data.sentiment.news_articles);

                // Prediction
                const pred = data.prediction || {};
                const actionEl = document.getElementById('pred-action');
                actionEl.innerText = pred.action || 'HOLDING';
                if (pred.action === 'BUY') {
                    actionEl.style.color = 'var(--color-green)';
                } else if (pred.action === 'SELL') {
                    actionEl.style.color = 'var(--color-red)';
                } else {
                    actionEl.style.color = 'var(--text-muted)';
                }
                document.getElementById('pred-type').innerText = pred.setup_type || 'N/A';
                document.getElementById('pred-entry').innerText = pred.entry ? pred.entry.toFixed(5) : '--';
                document.getElementById('pred-sl').innerText = pred.sl ? pred.sl.toFixed(5) : '--';
                document.getElementById('pred-tp').innerText = pred.tp ? pred.tp.toFixed(5) : '--';
                document.getElementById('pred-lots').innerText = pred.lots ? pred.lots.toFixed(2) : '0.01';
                document.getElementById('pred-confidence').innerText = pred.confidence ? `${pred.confidence}%` : '—';

                // Active Sessions — read from top-level (fixed: previously read from pred which could be empty)
                const sessions = data.active_sessions || pred.active_sessions || [];
                const sessionColors = {
                    'Sydney': '#a855f7',
                    'Asian': '#f59e0b',
                    'London': '#3b82f6',
                    'New York': '#10b981'
                };
                const sessionHTML = sessions.length > 0
                    ? sessions.map(s => `<span style="background: rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.18); border: 1px solid rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.5); border-radius: 5px; padding: 3px 9px; font-size: 11px; font-weight: 700; color: ${sessionColors[s]||'var(--color-blue)'}; margin-right: 5px; text-shadow: 0 0 6px currentColor;">${s}</span>`).join('')
                    : '<span style="color:var(--text-muted);">NO SESSION</span>';
                document.getElementById('pred-sessions').innerHTML = sessionHTML;

                const headerSessionsEl = document.getElementById('header-sessions');
                if (headerSessionsEl) {
                    headerSessionsEl.innerHTML = sessions.length > 0
                        ? sessions.map(s => `<span style="background: rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.18); border: 1px solid rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.5); border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 700; color: ${sessionColors[s]||'var(--color-blue)'}; text-shadow: 0 0 6px currentColor; display: inline-block;">${s}</span>`).join('')
                        : '<span style="color:var(--text-muted); font-size: 11px; font-weight: 600;">NO ACTIVE SESSIONS</span>';
                }

                // ── 6-TF Cascade Alignment Panel ─────────────────────────────
                const tfAlign = pred.tf_alignment || data.tf_alignment || {};
                const biasLabel = (b, custom) => {
                    if (custom) return custom;
                    if (b > 0) return 'BULLISH';
                    if (b < 0) return 'BEARISH';
                    return 'NEUTRAL';
                };
                const biasColor = (b, lbl) => {
                    if (lbl && (lbl.includes('SWEEP') || lbl.includes('MSS') || lbl.includes('TBS'))) return '#ffd32a';
                    if (b > 0) return 'var(--color-green)';
                    if (b < 0) return 'var(--color-red)';
                    return 'var(--text-muted)';
                };

                const tfsToUpdate = [
                    {id: 'align-d1',  key: 'D1',  defaultBias: pred.d1_bias || 0},
                    {id: 'align-h4',  key: 'H4',  defaultBias: pred.h4_bias || 0},
                    {id: 'align-htf', key: 'H1',  defaultBias: pred.h1_bias || 0},
                    {id: 'align-ctx', key: 'M15', defaultBias: pred.m15_bias || 0},
                    {id: 'align-m5',  key: 'M5',  defaultBias: pred.m5_bias || 0},
                    {id: 'align-ltf', key: 'M1',  defaultBias: pred.m1_bias || 0},
                ];

                tfsToUpdate.forEach(({id, key, defaultBias}) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    const tfData = tfAlign[key] || {};
                    const bias = tfData.bias !== undefined ? tfData.bias : defaultBias;
                    const lbl = tfData.label || biasLabel(bias);
                    el.innerText = lbl;
                    el.style.color = biasColor(bias, lbl);
                    // Add a subtle glow for active signals
                    el.style.textShadow = bias !== 0 ? `0 0 8px ${biasColor(bias, lbl)}` : 'none';
                });

                // Alignment status indicator
                const isAligned = tfAlign.aligned || false;
                const alignStatusEl = document.getElementById('align-status');
                if (alignStatusEl) {
                    alignStatusEl.innerText = isAligned ? '✅ ALIGNED' : '⏳ SCANNING';
                    alignStatusEl.style.color = isAligned ? 'var(--color-green)' : 'var(--text-muted)';
                    alignStatusEl.style.textShadow = isAligned ? '0 0 10px var(--glow-green)' : 'none';
                }

                // Skip logs
                const skipped = data.skipped_stats || {};
                document.getElementById('skip-spread').innerText = skipped.high_spread || 0;
                document.getElementById('skip-news').innerText = skipped.news_filter || 0;

                // Positions Table
                const posBody = document.getElementById('positions-body');
                if (data.positions && data.positions.length > 0) {
                    posBody.innerHTML = data.positions.map(p => `
                        <tr>
                            <td>${p.id}</td>
                            <td>${p.symbol}</td>
                            <td style="color:${p.action === 'BUY' ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">${p.action}</td>
                            <td>${p.volume.toFixed(2)}</td>
                            <td>${p.entry_price.toFixed(5)}</td>
                            <td>${p.sl.toFixed(5)}</td>
                            <td>${p.tp.toFixed(5)}</td>
                            <td style="color:${p.pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${p.pnl.toFixed(2)}</td>
                        </tr>
                    `).join('');
                } else {
                    posBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No open positions.</td></tr>`;
                }

                // History Table
                const histBody = document.getElementById('history-body');
                if (data.history && data.history.length > 0) {
                    histBody.innerHTML = data.history.slice(-6).reverse().map(h => `
                        <tr>
                            <td>${h.id}</td>
                            <td>${h.symbol}</td>
                            <td style="color:${h.action === 'BUY' ? 'var(--color-green)' : 'var(--color-red)'};">${h.action}</td>
                            <td>${h.volume.toFixed(2)}</td>
                            <td>${h.entry_price.toFixed(5)}</td>
                            <td>${h.close_price.toFixed(5)}</td>
                            <td>${h.close_reason}</td>
                            <td style="color:${h.pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${h.pnl.toFixed(2)}</td>
                        </tr>
                    `).join('');
                } else {
                    histBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No closed trades yet.</td></tr>`;
                }

                // Volume stats
                const vol = data.volume || {};
                document.getElementById('val-rvol').innerText = (vol.rvol || 1.0).toFixed(2);
                
                const rvolBadge = document.getElementById('badge-rvol');
                if (vol.rvol > 1.3) {
                    rvolBadge.innerText = 'EXPANSION';
                    rvolBadge.style.backgroundColor = 'rgba(0, 240, 118, 0.15)';
                    rvolBadge.style.color = 'var(--color-green)';
                    rvolBadge.style.borderColor = 'var(--color-green)';
                } else {
                    rvolBadge.innerText = 'NORMAL';
                    rvolBadge.style.backgroundColor = 'rgba(0, 168, 255, 0.15)';
                    rvolBadge.style.color = 'var(--color-blue)';
                    rvolBadge.style.borderColor = 'var(--color-blue)';
                }
                
                const buyPct = Math.round(vol.buy_pressure || 50.0);
                const sellPct = 100 - buyPct;
                document.getElementById('lbl-pressure-buy').innerText = `${buyPct}%`;
                document.getElementById('lbl-pressure-sell').innerText = `${sellPct}%`;
                document.getElementById('bar-pressure-buy').style.width = `${buyPct}%`;

                // Volume Profile Poc Histogram
                const container = document.getElementById('vp-chart-container');
                if (container && vol.profile && vol.profile.bin_volumes && vol.profile.bin_volumes.length > 0) {
                    const profile = vol.profile;
                    const volumes = profile.bin_volumes;
                    const edges = profile.bin_edges;
                    const max_vol = Math.max(...volumes, 1.0);
                    const poc = profile.poc_price;
                    
                    let html = "";
                    for (let i = volumes.length - 1; i >= 0; i--) {
                        const binPriceLow = edges[i];
                        const binPriceHigh = edges[i+1];
                        const binMid = (binPriceLow + binPriceHigh) / 2.0;
                        const isPoc = Math.abs(binMid - poc) < (binPriceHigh - binPriceLow)/2.0;
                        const width_pct = (volumes[i] / max_vol) * 100.0;
                        
                        html += `
                            <div class="vp-bar-row ${isPoc ? 'poc' : ''}">
                                <div class="vp-price">${binMid.toFixed(2)}</div>
                                <div class="vp-bar-fill" style="width: ${width_pct.toFixed(1)}%"></div>
                            </div>
                        `;
                    }
                    container.innerHTML = html;
                }

                // Settings
                document.getElementById('toggle-autotrade').checked = settings.auto_trade_enabled !== false;
                document.getElementById('toggle-paper').checked = settings.paper_mode || false;
                document.getElementById('toggle-compounding').checked = settings.compounding_mode || false;
                document.getElementById('toggle-hedging').checked = settings.hedging_mode || false;
                document.getElementById('toggle-trailing').checked = settings.trailing_stop_enabled || false;
                document.getElementById('toggle-breakeven').checked = settings.break_even_enabled || false;
                document.getElementById('toggle-news-filter').checked = settings.news_filter_enabled || false;
                document.getElementById('toggle-self-learning').checked = settings.self_learning_filter || false;

                document.getElementById('input-risk').value = settings.risk_percent || 1.0;
                document.getElementById('lbl-risk-val').innerText = `${(settings.risk_percent || 1.0).toFixed(2)}%`;
                document.getElementById('input-max-daily').value = settings.max_daily_trades || 3;
                document.getElementById('lbl-max-daily-val').innerText = settings.max_daily_trades || 3;

                document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
                const actMode = settings.trading_mode || 'intraday';
                document.getElementById(`btn-mode-${actMode}`).classList.add('active');

                // News Ribbon Update
                const newsTicker = document.getElementById('news-ticker-wrap');
                if (newsTicker && data.sentiment.news_articles && data.sentiment.news_articles.length > 0) {
                    newsTicker.innerHTML = data.sentiment.news_articles.map(art => `
                        <span class="ticker-item"><strong style="color: var(--color-gold);">•</strong> ${art.title}</span>
                    `).join('');
                }

                // Caution Ribbon Update
                const cautionTicker = document.getElementById('caution-ticker-wrap');
                if (cautionTicker) {
                    let warnings = [];
                    if (data.spread && data.spread.exceeded) {
                        warnings.push(`🚨 SPREAD LIMIT EXCEEDED ON ${data.spread.symbol}: ${data.spread.current} PTS (MAX ALLOWED: ${data.spread.max_limit})`);
                    }
                    if (data.margin_level !== 'N/A' && parseFloat(data.margin_level) < 200.0) {
                        warnings.push(`🚨 MARGIN LEVEL IS EXTREMELY LOW: ${data.margin_level} — SUSPENDING NEW TRADES`);
                    }
                    if (data.positions && data.positions.length > 0) {
                        warnings.push(`💼 MONITORING ${data.positions.length} ACTIVE TRADES — FLOATING PNL: $${data.account.profit.toFixed(2)}`);
                    }
                    warnings.push("🛡️ VOLUME DISASTER SAFETY SYSTEM: BYPASSED PER USER REQUEST TO PREVENT WICK TRAPS");
                    warnings.push("📈 AI SELF-LEARNING NAIVE BAYES CLASSIFIER CONTROLLING INTRADAY/SCALPING ENTRY BIAS");
                    warnings.push(`🧬 SCANNING SWING POINTS AND ORDER BLOCKS ON THE 1-MINUTE TIMEFRAME FOR ${data.spread.symbol || 'ACTIVE PAIR'}`);
                    
                    cautionTicker.innerHTML = warnings.map(w => `
                        <span class="ticker-item">${w}</span>
                    `).join('');
                }

                // Upcoming events calendar rendering
                const calList = document.getElementById('calendar-events-list');
                if (calList && data.sentiment.upcoming_events) {
                    const symbol = document.getElementById('symbol-select').value;
                    calList.innerHTML = data.sentiment.upcoming_events.map(ev => {
                        const impactColor = ev.impact === 'HIGH' ? 'var(--color-red)' : 'var(--color-gold)';
                        const isPast = ev.status === 'PAST WEEK';
                        
                        let badgeHtml = '';
                        let bgStyle = 'background: rgba(255, 255, 255, 0.02);';
                        let borderStyle = 'border: 1px solid var(--glass-border);';
                        
                        if (isPast) {
                            bgStyle = 'background: rgba(255, 255, 255, 0.01);';
                            borderStyle = 'border: 1px solid rgba(255, 255, 255, 0.02);';
                            badgeHtml = `
                                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 9px; color: var(--text-muted); margin-top: 4px;">
                                    <span>⏰ ${ev.date} (${ev.currency})</span>
                                    <span style="color: var(--text-muted); font-weight: 600;">ACT: <span style="color: var(--text-primary);">${ev.actual}</span> vs CONS: ${ev.consensus}</span>
                                </div>
                            `;
                        } else {
                            const pred = ev.pair_forecasts[symbol] || 'NEUTRAL';
                            let predColor = 'var(--text-muted)';
                            let predBadge = 'NEUTRAL';
                            if (pred === 'BULLISH') {
                                predColor = 'var(--color-green)';
                                predBadge = 'BULL';
                            } else if (pred === 'BEARISH') {
                                predColor = 'var(--color-red)';
                                predBadge = 'BEAR';
                            }
                            const statusLabel = ev.status === 'THIS WEEK' ? 'CURRENT' : 'UPCOMING';
                            badgeHtml = `
                                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 9px; color: var(--text-muted); margin-top: 4px;">
                                    <span>⏰ ${ev.date} (${ev.currency})</span>
                                    <span>Cons: <strong>${ev.consensus}</strong></span>
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 9px; color: var(--text-muted); margin-top: 2px;">
                                    <span style="font-size: 8px; font-weight: 700; color: ${ev.status === 'THIS WEEK' ? 'var(--color-blue)' : 'var(--text-muted)'};">${statusLabel}</span>
                                    <span>Forecast: <strong style="color: ${predColor};">${predBadge}</strong></span>
                                </div>
                            `;
                        }
                        
                        return `
                            <div style="${bgStyle} ${borderStyle} padding: 8px; border-radius: 8px; display: flex; flex-direction: column; gap: 2px; font-size: 11px; opacity: ${isPast ? 0.65 : 1.0};">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-weight: 700; color: ${isPast ? 'var(--text-muted)' : 'var(--text-primary)'}; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 170px;" title="${ev.event}">${ev.event}</span>
                                    <span style="font-size: 8px; font-weight: 800; padding: 1px 4px; border-radius: 3px; background: ${impactColor}15; color: ${impactColor}; border: 1px solid ${impactColor}30;">${ev.impact}</span>
                                </div>
                                ${badgeHtml}
                            </div>
                        `;
                    }).join('');
                }

                // Update Prediction card patterns, regime, and training stats
                if (pred.detected_patterns && pred.detected_patterns.length > 0) {
                    document.getElementById('pred-patterns').innerText = pred.detected_patterns.join(', ');
                } else {
                    document.getElementById('pred-patterns').innerText = 'NONE';
                }
                const clusters = {
                    0: 'Consolidation (Cluster 0)',
                    1: 'Expansion (Cluster 1)',
                    2: 'Volatile Chop (Cluster 2)',
                    3: 'Trend Reversal (Cluster 3)'
                };
                document.getElementById('pred-regime').innerText = clusters[pred.cluster_id] || 'RANGING';

                const trainStatsEl = document.getElementById('pred-train-stats');
                if (trainStatsEl) {
                    const stats = pred.training_stats;
                    if (stats && stats.total_samples !== undefined && stats.total_samples > 0) {
                        trainStatsEl.innerHTML = `Samples: <strong style="color:var(--text-primary);">${stats.total_samples}</strong> | Win Rate: <strong style="color:var(--color-green);">${stats.win_rate}%</strong> (W:${stats.wins} L:${stats.losses})<br><span style="color:var(--text-muted); font-size:9px;">Last trained: ${stats.last_train_time}</span>`;
                    } else {
                        trainStatsEl.innerText = 'No training history found.';
                    }
                }

                // Safety Diagnostics Updates
                const mt5El = document.getElementById('diag-mt5');
                if (data.account.broker === 'ERROR') {
                    mt5El.innerText = 'DISCONNECTED 🔴';
                    mt5El.style.color = 'var(--color-red)';
                } else {
                    mt5El.innerText = 'CONNECTED 🟢';
                    mt5El.style.color = 'var(--color-green)';
                }

                const marginEl = document.getElementById('diag-margin');
                if (data.margin_level !== 'N/A' && parseFloat(data.margin_level) < 200.0) {
                    marginEl.innerText = 'LOW MARGIN ⚠️';
                    marginEl.style.color = 'var(--color-red)';
                } else {
                    marginEl.innerText = 'PASSED 🟢';
                    marginEl.style.color = 'var(--color-green)';
                }

                // Update Leverage & Margin Level & Equity/Balance
                document.getElementById('diag-leverage').innerText = data.leverage || 'N/A';
                document.getElementById('diag-margin-level').innerText = data.margin_level || 'N/A';
                
                const marginLevelVal = parseFloat(data.margin_level);
                const marginLevelEl = document.getElementById('diag-margin-level');
                if (!isNaN(marginLevelVal) && marginLevelVal < 200.0) {
                    marginLevelEl.style.color = 'var(--color-red)';
                } else if (!isNaN(marginLevelVal) && marginLevelVal < 500.0) {
                    marginLevelEl.style.color = 'var(--color-gold)';
                } else {
                    marginLevelEl.style.color = 'var(--color-green)';
                }
                
                const bal = data.account.balance || 0;
                const eq = data.account.equity || 0;
                const pnl = data.account.profit || 0;
                document.getElementById('diag-equity-bal').innerHTML = `<span style="color:${pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${eq.toFixed(2)}</span> / $${bal.toFixed(2)}`;

                const dailyEl = document.getElementById('diag-daily');
                const maxDaily = data.settings.max_daily_trades || 3;
                const todayStr = new Date().toISOString().slice(0, 10);
                const tradesToday = data.history ? data.history.filter(h => h.close_time && h.close_time.slice(0, 10) === todayStr).length : 0;
                if (data.skipped_stats.max_daily_reached || tradesToday >= maxDaily) {
                    dailyEl.innerText = 'LIMIT REACHED 🛑';
                    dailyEl.style.color = 'var(--color-red)';
                } else {
                    dailyEl.innerText = 'PASSED 🟢';
                    dailyEl.style.color = 'var(--color-green)';
                }

                const spreadEl = document.getElementById('diag-spread');
                if (data.spread && data.spread.exceeded) {
                    spreadEl.innerText = 'HIGH SPREAD ⚠️';
                    spreadEl.style.color = 'var(--color-red)';
                } else {
                    spreadEl.innerText = 'PASSED 🟢';
                    spreadEl.style.color = 'var(--color-green)';
                }

                const newsEl = document.getElementById('diag-news');
                if (data.settings.news_filter_enabled && Math.abs(data.sentiment.news) > 0.6) {
                    newsEl.innerText = 'NEWS VOLATILE 🛑';
                    newsEl.style.color = 'var(--color-gold)';
                } else {
                    newsEl.innerText = 'PASSED 🟢';
                    newsEl.style.color = 'var(--color-green)';
                }

                const aiEl = document.getElementById('diag-ai');
                if (pred.confidence && pred.confidence > 0.0) {
                    if (pred.confidence >= 58.0) {
                        aiEl.innerText = 'CONFIDENT BUY 🟢';
                        aiEl.style.color = 'var(--color-green)';
                    } else if (pred.confidence <= 42.0) {
                        aiEl.innerText = 'CONFIDENT SELL 🔴';
                        aiEl.style.color = 'var(--color-red)';
                    } else {
                        aiEl.innerText = 'HOLDING ⚪';
                        aiEl.style.color = 'var(--text-muted)';
                    }
                } else {
                    aiEl.innerText = 'SCANNING 🔍';
                    aiEl.style.color = 'var(--color-blue)';
                }

                // Client-side instant candle update from polling ticks
                if (data.spread && data.spread.bid && canvasChart && canvasChart.candles && canvasChart.candles.length > 0) {
                    const bid = data.spread.bid;
                    let lastCandle = canvasChart.candles[canvasChart.candles.length - 1];
                    lastCandle.close = bid;
                    if (bid > lastCandle.high) lastCandle.high = bid;
                    if (bid < lastCandle.low) lastCandle.low = bid;
                    
                    canvasChart.bidPrice = bid;
                    canvasChart.askPrice = data.spread.ask;
                    
                    canvasChart.draw();
                }

            } catch (e) {
                console.error("Failed to poll status", e);
                // Visual feedback for connection failure
                document.getElementById('broker-name').innerText = 'DISCONNECTED 🔴';
                document.getElementById('broker-name').style.color = 'var(--color-red)';
                document.getElementById('latency-lbl').innerText = `LATENCY: --`;
                document.getElementById('spread-lbl').innerText = `SPREAD: --`;
                
                const mt5El = document.getElementById('diag-mt5');
                if (mt5El) {
                    mt5El.innerText = 'DISCONNECTED 🔴';
                    mt5El.style.color = 'var(--color-red)';
                }
            }
        }

        function updateDial(id, valId, score, isNews = false) {
            const dial = document.getElementById(id);
            const valEl = document.getElementById(valId);
            if (!dial || !valEl) return;

            const percent = ((score + 1.0) / 2.0) * 100;
            if (isNews) {
                valEl.innerText = score.toFixed(2);
            } else {
                valEl.innerText = `${Math.round(score * 100)}%`;
            }

            const filled = (percent / 100) * 94; // 94 units max for cx=35 r=30
            dial.style.strokeDasharray = `${filled} 188`;

            let color = 'var(--text-muted)';
            if (score > 0.15) {
                color = 'var(--color-green)';
            } else if (score < -0.15) {
                color = 'var(--color-red)';
            }
            dial.style.stroke = color;

            const dirId = valId.replace('val-', 'dir-');
            const dirEl = document.getElementById(dirId);
            if (dirEl) {
                if (score > 0.15) {
                    dirEl.innerText = '▲ Bullish';
                    dirEl.style.color = 'var(--color-green)';
                } else if (score < -0.15) {
                    dirEl.innerText = '▼ Bearish';
                    dirEl.style.color = 'var(--color-red)';
                } else {
                    dirEl.innerText = '◆ Neutral';
                    dirEl.style.color = 'var(--text-muted)';
                }
            }
        }

        function updateNewsDrawer(articles) {
            const list = document.getElementById('drawer-news-list');
            if (!list) return;

            if (articles && articles.length > 0) {
                list.innerHTML = articles.map((art, idx) => {
                    const score = art.sentiment || 0;
                    let impactClass = 'low';
                    if (Math.abs(score) > 0.4) impactClass = 'high';
                    else if (Math.abs(score) > 0.15) impactClass = 'medium';
                    
                    return `
                        <div class="news-item" onclick="toggleNewsDesc(${idx})">
                            <div class="news-meta">
                                <span style="color:var(--text-muted);">${art.date || ''}</span>
                                <span class="ticker-badge ${impactClass}">${impactClass.toUpperCase()}</span>
                            </div>
                            <div class="news-title">${art.title}</div>
                            <div class="news-desc" id="news-desc-${idx}">${art.description || 'No description available.'}</div>
                        </div>
                    `;
                }).join('');
            } else {
                list.innerHTML = `<span style="color: var(--text-muted); font-size: 11px;">No news loaded yet.</span>`;
            }
        }

        function toggleNewsDesc(idx) {
            const el = document.getElementById(`news-desc-${idx}`);
            if (el) el.classList.toggle('open');
        }

        async function toggleSetting(key) {
            let chk = false;
            if (key === 'auto_trade_enabled') chk = document.getElementById('toggle-autotrade').checked;
            else if (key === 'paper_mode') chk = document.getElementById('toggle-paper').checked;
            else if (key === 'compounding_mode') chk = document.getElementById('toggle-compounding').checked;
            else if (key === 'hedging_mode') chk = document.getElementById('toggle-hedging').checked;
            else if (key === 'trailing_stop_enabled') chk = document.getElementById('toggle-trailing').checked;
            else if (key === 'break_even_enabled') chk = document.getElementById('toggle-breakeven').checked;
            else if (key === 'news_filter_enabled') chk = document.getElementById('toggle-news-filter').checked;
            else if (key === 'self_learning_filter') chk = document.getElementById('toggle-self-learning').checked;
            sendSettingUpdate({ [key]: chk });
        }

        async function setTradingMode(mode) {
            sendSettingUpdate({ "trading_mode": mode });
        }

        function updateRiskValue(val) {
            document.getElementById('lbl-risk-val').innerText = `${parseFloat(val).toFixed(2)}%`;
        }

        async function saveRiskSetting(val) {
            sendSettingUpdate({ "risk_percent": parseFloat(val) });
        }

        function updateMaxDailyValue(val) {
            document.getElementById('lbl-max-daily-val').innerText = val;
        }

        async function saveMaxDailySetting(val) {
            sendSettingUpdate({ "max_daily_trades": parseInt(val) });
        }

        async function sendSettingUpdate(payload) {
            try {
                const response = await fetch(`${apiBase}/api/settings`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (response.ok) fetchStatus();
            } catch (e) {
                console.error("Failed to update setting", e);
            }
        }

        async function triggerTraining() {
            try {
                const response = await fetch(`${apiBase}/api/train`, { method: 'POST' });
                if (response.ok) alert("AI Auto-Training Job triggered successfully!");
            } catch (e) {
                console.error("Failed to trigger training", e);
            }
        }

        async function panicCloseAll() {
            if (confirm("🚨 EMERGENCY: Are you sure you want to close ALL active positions?")) {
                try {
                    const response = await fetch(`${apiBase}/api/close_all`, { method: 'POST' });
                    if (response.ok) {
                        const result = await response.json();
                        alert(`Panic close completed successfully!\nClosed positions: ${result.closed.join(', ')}`);
                        fetchStatus();
                    }
                } catch (e) {
                    console.error("Failed to panic close", e);
                }
            }
        }
    </script>
</body>
</html>
"""
