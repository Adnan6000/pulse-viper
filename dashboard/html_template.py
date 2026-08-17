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

        @media (max-width: 768px) {
            .main-dashboard {
                padding: 12px 16px;
                gap: 16px;
            }
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--glass-border);
            padding-bottom: 16px;
            position: sticky;
            top: 0;
            z-index: 1000;
            background: rgba(7, 10, 19, 0.95);
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

        /* ── Regime Pills & News Lockout Animations ────────── */
        .regime-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 700;
            text-align: center;
            border: 1px solid transparent;
            box-shadow: 0 0 10px rgba(255, 255, 255, 0.05);
            transition: all 0.3s ease;
        }
        .regime-trending {
            background: rgba(46, 204, 113, 0.15);
            color: var(--color-green) !important;
            border-color: rgba(46, 204, 113, 0.3);
            box-shadow: 0 0 15px rgba(46, 204, 113, 0.25);
        }
        .regime-range {
            background: rgba(255, 215, 0, 0.15);
            color: var(--color-gold) !important;
            border-color: rgba(255, 215, 0, 0.3);
            box-shadow: 0 0 15px rgba(255, 215, 0, 0.2);
        }
        .regime-compression {
            background: rgba(0, 210, 211, 0.15);
            color: var(--color-blue) !important;
            border-color: rgba(0, 210, 211, 0.3);
            box-shadow: 0 0 15px rgba(0, 210, 211, 0.25);
        }
        .regime-chaotic {
            background: rgba(255, 71, 87, 0.15);
            color: var(--color-red) !important;
            border-color: rgba(255, 71, 87, 0.3);
            box-shadow: 0 0 15px rgba(255, 71, 87, 0.3);
            animation: pulse-red-scale 1.5s infinite alternate;
        }
        @keyframes pulse-red-scale {
            0% { transform: scale(1.0); }
            100% { transform: scale(1.05); }
        }
        @keyframes pulse-red-bg {
            0% { border-color: rgba(255, 71, 87, 0.3); box-shadow: 0 0 15px rgba(255, 71, 87, 0.1); }
            100% { border-color: rgba(255, 71, 87, 0.6); box-shadow: 0 0 25px rgba(255, 71, 87, 0.3); }
        }
        @keyframes rotate-warning {
            0% { transform: scale(1.0); }
            50% { transform: scale(1.2); }
            100% { transform: scale(1.0); }
        }

        /* ── Three-Column Main Content Grid ───────────────── */
        .dashboard-container {
            display: grid;
            grid-template-columns: 340px 1fr 340px;
            gap: 20px;
            width: 100%;
        }

        @media (max-width: 1400px) {
            .dashboard-container {
                grid-template-columns: 280px 1fr 280px;
                gap: 16px;
            }
        }

        @media (max-width: 1280px) {
            .main-dashboard {
                padding: 16px 20px;
                gap: 20px;
            }
            .dashboard-container {
                grid-template-columns: 1fr 300px;
                gap: 16px;
            }
            #sentiment-card {
                grid-column: 2;
                grid-row: 1;
            }
            #middle-column {
                grid-column: 1;
                grid-row: 1 / span 2;
            }
            #right-column {
                grid-column: 2;
                grid-row: 2;
            }
        }

        @media (max-width: 1024px) {
            .dashboard-container {
                grid-template-columns: 1fr;
                gap: 20px;
            }
            #sentiment-card {
                grid-column: auto;
                grid-row: auto;
            }
            #middle-column {
                grid-column: auto;
                grid-row: auto;
            }
            #right-column {
                grid-column: auto;
                grid-row: auto;
            }
            .chart-holder {
                height: 500px !important;
            }
        }

        @media (max-width: 768px) {
            .main-dashboard {
                padding: 12px 16px;
                gap: 16px;
            }
            .chart-holder {
                height: 60vh !important;
                min-height: 400px !important;
            }
            .logo-section h1 {
                font-size: 18px;
            }
            .tf-btn, .tool-btn {
                padding: 5px 10px;
                font-size: 11px;
            }
        }

        @media (max-width: 480px) {
            .chart-holder {
                height: 50vh !important;
                min-height: 350px !important;
            }
            header {
                flex-direction: column;
                align-items: flex-start;
            }
            .status-badge {
                width: 100%;
                justify-content: center;
            }
        }

        /* For full-screen mode on any device */
        #chart-card:fullscreen {
            display: flex !important;
            flex-direction: column !important;
            height: 100vh !important;
            width: 100vw !important;
            background: #070a13 !important; /* matches var(--bg-dark) */
            padding: 16px !important;
            border-radius: 0 !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
            gap: 12px !important;
        }

        #chart-card:fullscreen .fullscreen-only-header {
            display: flex !important;
        }

        #chart-card:fullscreen .chart-header {
            padding: 0 !important;
            margin: 0 !important;
            background: transparent !important;
            border: none !important;
        }

        #chart-card:fullscreen .chart-holder {
            flex: 1 1 auto !important;
            height: auto !important;
            border-radius: 8px !important;
            background: rgba(0, 0, 0, 0.4) !important;
            border: 1px solid var(--glass-border) !important;
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
            flex-wrap: wrap;
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
            justify-content: center;
            background: rgba(0,0,0,0.15);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 10px;
            gap: 4px;
            box-sizing: border-box;
            width: 100%;
            height: 100%;
            min-height: 96px;
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

        .drawer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            padding-bottom: 12px;
            margin-bottom: 10px;
        }

        .drawer-header h3 {
            margin: 0;
            font-size: 18px;
            color: var(--text-primary);
        }

        .drawer-close {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 20px;
            cursor: pointer;
            padding: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            border-radius: 4px;
        }

        .drawer-close:hover {
            color: var(--color-red);
            background: rgba(255, 51, 102, 0.1);
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
            margin-bottom: 8px;
            width: 100%;
            background: rgba(7, 10, 19, 0.95);
            padding-top: 8px;
            padding-bottom: 8px;
            position: relative;
            z-index: 10;
            clear: both;
        }
        .ticker-row {
            overflow: hidden;
            white-space: nowrap;
            display: flex;
            align-items: center;
            height: 42px;
            border-radius: 6px;
            border: 1px solid var(--glass-border);
            font-size: 16px;
            font-weight: 600;
            letter-spacing: 0.5px;
            position: relative;
            z-index: 10;
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
            padding: 0 14px;
            height: 100%;
            display: flex;
            align-items: center;
            z-index: 10;
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            border-radius: 5px 0 0 5px;
            flex-shrink: 0;
            position: absolute;
            left: 0;
            box-shadow: 4px 0 10px rgba(0,0,0,0.5);
        }
        .caution-ticker .ticker-header {
            background: #8b1029;
            border-right: 1px solid rgba(255, 71, 87, 0.6);
            color: #ffffff;
        }
        .news-ticker .ticker-header {
            background: #7a5e00;
            border-right: 1px solid rgba(255, 215, 0, 0.6);
            color: #ffffff;
        }
        .ticker-wrap {
            display: inline-block;
            white-space: nowrap;
            padding-left: 100%;
            animation: marquee 90s linear infinite;
        }
        .news-ticker .ticker-wrap {
            animation-duration: 150s;
        }
        @keyframes marquee {
            0% { transform: translate3d(0, 0, 0); }
            100% { transform: translate3d(-100%, 0, 0); }
        }
        .ticker-item {
            display: inline-block;
            padding: 0 30px;
        }
        body.is-fullscreen .hide-on-fullscreen {
            display: none !important;
        }
    </style>
</head>
<body>
    
    <!-- Global JavaScript Error catching banner -->
    <script nonce="{{NONCE}}">
        window.onerror = function(message, source, lineno, colno, error) {
            if (message && (message.indexOf('ResizeObserver loop completed with undelivered notifications') !== -1 || message.indexOf('ResizeObserver loop limit exceeded') !== -1)) {
                return false;
            }
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
    <div class="config-overlay" id="config-overlay"></div>
    <div class="config-drawer" id="config-drawer">
        <div class="drawer-header">
            <h3>⚙️ Configurations</h3>
            <button class="drawer-close" id="drawer-close-btn">✕</button>
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
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Strict Veto Mode</span>
                    <span class="setting-desc">Instantly block entries if any filter vetoes</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-strict-mode" onchange="toggleSetting('strict_mode')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Dynamic Risk Sizing</span>
                    <span class="setting-desc">Scale risk dynamically on spread/volatility</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-dynamic-risk" onchange="toggleSetting('dynamic_risk_enabled')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Dynamic Regime Filter</span>
                    <span class="setting-desc">Block entries during chaotic/consolidation phases</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-regime-filter" onchange="toggleSetting('dynamic_regime_filter')">
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
                <input type="range" id="input-risk" min="0.1" max="5.0" step="0.1" value="0.1" oninput="updateRiskValue(this.value)" onchange="saveRiskSetting(this.value)">
                <span id="lbl-risk-val" style="font-weight:700;">0.1%</span>
            </div>
            
            <div class="setting-row" style="margin-top:10px;">
                <div class="setting-info">
                    <span class="setting-name">Use Manual Lot Size</span>
                    <span class="setting-desc">Use fixed lot instead of risk-based sizing</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-manual-lot" onchange="toggleSetting('use_manual_lot')">
                    <span class="slider"></span>
                </label>
            </div>
            <div class="setting-row" style="margin-top:5px;">
                <div class="setting-info">
                    <span class="setting-name">Manual Lot Size</span>
                    <span class="setting-desc">Fixed lot size when manual mode is enabled</span>
                </div>
            </div>
            <div class="range-slider-container" style="display: flex; align-items: center; gap: 8px;">
                <input type="range" id="input-manual-lot" min="0.01" max="100.0" step="0.01" value="0.01" style="flex-grow: 1;" oninput="updateManualLotValue(this.value)" onchange="saveManualLotSetting(this.value)">
                <input type="number" id="input-manual-lot-num" min="0.01" max="1000.0" step="0.01" value="0.01" style="background: rgba(0,0,0,0.3); border: 1px solid var(--glass-border); color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 600; outline: none; width: 65px; padding: 4px 6px; border-radius: 6px; text-align: center;" oninput="updateManualLotValue(this.value)" onchange="saveManualLotSetting(this.value)">
                <span id="lbl-manual-lot-val" style="font-weight:700; font-size: 11px; white-space: nowrap;">0.01 lots</span>
            </div>
            
            <div class="setting-row" style="margin-top:10px;">
                <div class="setting-info">
                    <span class="setting-name">Min AI Confidence</span>
                    <span class="setting-desc">Minimum pattern learner confidence to allow trades</span>
                </div>
            </div>
            <div class="range-slider-container">
                <input type="range" id="input-min-ai-conf" min="0.00" max="1.00" step="0.01" value="0.52" oninput="updateMinAIConfValue(this.value)" onchange="saveMinAIConfSetting(this.value)">
                <span id="lbl-min-ai-conf-val" style="font-weight:700;">0.52</span>
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
            <div class="setting-row" style="margin-top:10px;">
                <div class="setting-info">
                    <span class="setting-name">Max Spread Points</span>
                    <span class="setting-desc">Max spread in points to permit trade entries</span>
                </div>
            </div>
            <div class="range-slider-container" style="display: flex; align-items: center; gap: 8px;">
                <input type="range" id="input-max-spread" min="10" max="5000" step="10" value="300" style="flex-grow: 1;" oninput="updateMaxSpreadValue(this.value)" onchange="saveMaxSpreadSetting(this.value)">
                <input type="number" id="input-max-spread-num" min="1" max="100000" step="1" value="300" style="background: rgba(0,0,0,0.3); border: 1px solid var(--glass-border); color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 600; outline: none; width: 65px; padding: 4px 6px; border-radius: 6px; text-align: center;" oninput="updateMaxSpreadValue(this.value)" onchange="saveMaxSpreadSetting(this.value)">
                <span id="lbl-max-spread-val" style="font-weight:700; font-size: 11px; white-space: nowrap;">300 pts</span>
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
        <button class="btn-train" id="btn-trigger-training" onclick="triggerTraining()">Trigger AI Auto-Train</button>
        <button class="btn-panic" id="btn-reset-settings" onclick="resetSettings()" style="background: var(--color-orange);">Reset to Default</button>
        <button class="btn-panic" id="btn-panic-close" onclick="panicCloseAll()">Panic Close All</button>
    </div>

    <!-- ── Main Dashboard Panel ─────────────────────────── -->
    <div class="main-dashboard">
        <header>
            <div class="logo-section">
                <h1 id="main-header">⚡ PULSE VIPER <span style="font-size: 12px; color: var(--color-blue); letter-spacing: 0.5px; border: 1px solid var(--color-blue); padding: 2px 8px; border-radius: 4px;">QUANTUM EA</span></h1>
            </div>
            <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 8px; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 6px 12px; border-radius: 30px;">
                    <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">SYMBOL:</span>
                    <select id="symbol-select" onchange="changeSymbol(this.value)" style="background: transparent; border: none; color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 12px; font-weight: 700; outline: none; cursor: pointer;">
                        <option value="XAUUSDm" style="background: var(--bg-dark); color: var(--text-primary);">XAUUSDm</option>
                        <option value="BTCUSDm" style="background: var(--bg-dark); color: var(--text-primary);">BTCUSDm</option>
                        <option value="EURUSDm" style="background: var(--bg-dark); color: var(--text-primary);">EURUSDm</option>
                        <option value="GBPUSDm" style="background: var(--bg-dark); color: var(--text-primary);">GBPUSDm</option>
                        <option value="USDJPYm" style="background: var(--bg-dark); color: var(--text-primary);">USDJPYm</option>
                    </select>
                </div>
                <!-- OBS Broadcast Stream Chroma-Key Mode Selector -->
                <div style="display: flex; align-items: center; gap: 6px; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 6px 12px; border-radius: 30px;">
                    <span style="font-size: 10px; font-weight: 700; color: var(--color-gold);">📺 STREAM OVERLAY:</span>
                    <select id="obs-mode-select" onchange="changeObsOverlayMode(this.value)" style="background: transparent; border: none; color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 700; outline: none; cursor: pointer;">
                        <option value="glass" style="background: var(--bg-dark); color: var(--text-primary);">Dark Glassmorphism</option>
                        <option value="chroma-green" style="background: var(--bg-dark); color: var(--text-primary);">Chroma-Key Green (#00ff00)</option>
                        <option value="chroma-magenta" style="background: var(--bg-dark); color: var(--text-primary);">Chroma-Key Magenta (#ff00ff)</option>
                        <option value="transparent" style="background: var(--bg-dark); color: var(--text-primary);">Transparent Overlay</option>
                    </select>
                </div>
                <div style="display: flex; align-items: center; gap: 4px; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 4px 8px; border-radius: 30px;">
                    <input type="text" id="custom-symbol-input" placeholder="Add Pair (e.g. XAUUSDc)" style="background: transparent; border: none; color: var(--text-primary); font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 600; outline: none; width: 140px; padding: 2px 4px;">
                    <button id="btn-add-custom-symbol" onclick="addCustomSymbol()" style="background: var(--color-blue); border: none; color: #070a13; font-weight: bold; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1.0)'" title="Add Custom Symbol">+</button>
                </div>
                <div class="status-badge" id="spread-badge">
                    <span id="spread-lbl">SPREAD: --</span>
                </div>
                <div class="status-badge" id="latency-badge">
                    <span id="latency-lbl">LATENCY: --</span>
                </div>
                <!-- <div class="status-badge">
                    <div class="status-dot"></div>
                    <span id="broker-name">DETECTING BROKER...</span>
                </div> -->
                <button class="gear-btn" id="gear-toggle-btn" title="Open Configuration Panel">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                </button>
            </div>
        </header>

        <!-- Session Banner Row with UTC and Local Clocks -->
        <div class="session-banner-row" style="display: flex; align-items: center; justify-content: space-between; background: var(--glass-bg); border: 1px solid var(--glass-border); padding: 8px 16px; border-radius: 12px; margin-bottom: 12px; flex-wrap: wrap; gap: 12px;">
            <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Active Sessions:</span>
                    <div id="header-sessions" style="display: flex; gap: 6px; align-items: center;">
                        <span style="color: var(--text-muted); font-size: 11px;">Loading sessions...</span>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; border-left: 1px solid rgba(255,255,255,0.08); padding-left: 16px;">
                    <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Session Quality:</span>
                    <span id="forex-session-badge" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 700; color: var(--text-muted); display: inline-block;">OFF (0.0 PTS)</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px;">
                    <span style="font-size: 10px; font-weight: 700; color: var(--text-muted);">SESSION REMAINING:</span>
                    <span id="session-remaining" style="font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 700; color: var(--color-gold); text-shadow: 0 0 6px rgba(245,158,11,0.3);">--:--</span>
                </div>
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
                <div class="ticker-header">⚠️ RISK DISCLAIMER</div>
                <div class="ticker-wrap" id="caution-ticker-wrap">
                    <span class="ticker-item">🎓 FOR EDUCATIONAL & RESEARCH PURPOSES ONLY — TAKE ALL TRADING RISKS AT YOUR OWN DISCRETION</span>
                    <span class="ticker-item">TRADING INVOLVES SUBSTANTIAL RISK OF LOSS — PAST PERFORMANCE IS NOT INDICATIVE OF FUTURE RESULTS</span>
                    <span class="ticker-item">PULSE VIPER IS AN EDUCATIONAL & QUANTITATIVE ANALYTICAL TOOL — DO NOT TRADE WITH MONEY YOU CANNOT AFFORD TO LOSE</span>
                    <span class="ticker-item">ALWAYS VERIFY SIGNALS WITH YOUR OWN INDEPENDENT ANALYSIS — NO STRATEGY GUARANTEES PROFIT</span>
                </div>
            </div>
            <div class="ticker-row news-ticker">
                <div class="ticker-header">📰 NEWS</div>
                <div class="ticker-wrap" id="news-ticker-wrap">
                    <span class="ticker-item" style="color: var(--text-muted);">No headlines loaded yet. Scraper starting...</span>
                </div>
            </div>
        </div>

        <!-- News Lockout Alert Banner -->
        <div id="news-lockout-banner" style="display: none; background: linear-gradient(90deg, rgba(255, 71, 87, 0.25), rgba(255, 71, 87, 0.05)); border: 1px solid rgba(255, 71, 87, 0.4); border-radius: 12px; padding: 12px 20px; align-items: center; gap: 15px; margin-bottom: 16px; box-shadow: 0 0 20px rgba(255, 71, 87, 0.2); animation: pulse-red-bg 2s infinite alternate;">
            <div style="font-size: 20px; animation: rotate-warning 1s infinite linear;">🚨</div>
            <div style="display: flex; flex-direction: column; gap: 2px; flex: 1;">
                <span style="font-weight: 700; font-size: 13px; color: var(--color-red); letter-spacing: 0.5px;">ECONOMIC NEWS LOCKOUT GATED ACTIVE</span>
                <span id="news-lockout-details" style="font-size: 11px; color: var(--text-muted);">US Core CPI YoY @ 12:30 UTC. New setups locked.</span>
            </div>
            <div style="font-size: 10px; font-weight: 800; background: var(--color-red); color: white; padding: 4px 8px; border-radius: 6px; text-transform: uppercase;">gated</div>
        </div>

        <!-- Phase 9: Brain Score Gauge Widget -->
        <div id="brain-score-widget" style="background: linear-gradient(135deg, rgba(15,20,40,0.95) 0%, rgba(20,15,45,0.95) 100%); border: 1px solid rgba(120, 100, 255, 0.3); border-radius: 14px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 0 30px rgba(100, 80, 255, 0.12); position: relative; overflow: hidden;">
            <!-- Decorative background glow -->
            <div style="position: absolute; top: -20px; right: -20px; width: 120px; height: 120px; background: radial-gradient(circle, rgba(100,80,255,0.15) 0%, transparent 70%); pointer-events: none;"></div>
            <div style="position: absolute; bottom: -20px; left: -20px; width: 80px; height: 80px; background: radial-gradient(circle, rgba(0,220,130,0.08) 0%, transparent 70%); pointer-events: none;"></div>

            <div style="display: flex; align-items: center; gap: 20px; position: relative; z-index: 1;">
                <!-- SVG Arc Gauge -->
                <div style="flex-shrink: 0; position: relative; width: 110px; height: 75px;">
                    <svg viewBox="0 0 120 80" width="110" height="75" style="overflow: visible;">
                        <!-- Track arc (grey) -->
                        <path d="M 10 70 A 55 55 0 0 1 110 70" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="10" stroke-linecap="round"/>
                        <!-- Gradient definitions -->
                        <defs>
                            <linearGradient id="brainGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                                <stop offset="0%" stop-color="#ff3366"/>
                                <stop offset="40%" stop-color="#ff8800"/>
                                <stop offset="70%" stop-color="#ffcc00"/>
                                <stop offset="100%" stop-color="#00ff88"/>
                            </linearGradient>
                        </defs>
                        <!-- Score arc (colored, animated) -->
                        <path id="brain-arc" d="M 10 70 A 55 55 0 0 1 110 70" fill="none" stroke="url(#brainGrad)" stroke-width="10" stroke-linecap="round"
                              stroke-dasharray="172.8" stroke-dashoffset="172.8" style="transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);"/>
                        <!-- Threshold marker -->
                        <circle id="brain-threshold-marker" cx="60" cy="15" r="3" fill="rgba(255,255,255,0.4)" style="transition: all 0.5s;"/>
                        <!-- Score text -->
                        <text x="60" y="62" text-anchor="middle" font-family="'Outfit', sans-serif" font-size="22" font-weight="800" fill="white" id="brain-score-text">0</text>
                        <text x="60" y="74" text-anchor="middle" font-family="'Inter', sans-serif" font-size="7" font-weight="600" fill="rgba(255,255,255,0.4)">/ 100</text>
                    </svg>
                    <!-- Label below gauge -->
                    <div id="brain-label-text" style="text-align: center; font-size: 9px; font-weight: 800; letter-spacing: 1px; margin-top: 2px; color: #ff3366; text-transform: uppercase; transition: color 0.5s;">BLOCKED</div>
                </div>

                <!-- Brain info panel -->
                <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-size: 14px;">&#129504;</span>
                            <span style="font-size: 12px; font-weight: 800; color: rgba(255,255,255,0.9); letter-spacing: 0.5px;">AI BRAIN SCORE</span>
                        </div>
                        <div id="brain-direction-badge" style="font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.4); border: 1px solid rgba(255,255,255,0.1); letter-spacing: 1px; transition: all 0.4s;">&#8212; IDLE</div>
                    </div>
                    <!-- Tier scores -->
                    <div style="display: flex; flex-direction: column; gap: 4px; margin-top: 1px;">
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 9px;">
                            <span style="width: 46px; color: rgba(255,255,255,0.4); font-weight: 700;">DIRECT</span>
                            <div style="flex:1; height: 5px; background: rgba(255,255,255,0.07); border-radius: 3px; overflow:hidden;">
                                <div id="brain-tier1-bar" style="height:100%; width:0%; background: #5577ff; border-radius:3px; transition:width 0.7s ease;"></div>
                            </div>
                            <span id="brain-tier1-val" style="width: 30px; text-align:right; color: rgba(255,255,255,0.55); font-weight:700;">0/50</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 9px;">
                            <span style="width: 46px; color: rgba(255,255,255,0.4); font-weight: 700;">EXEC</span>
                            <div style="flex:1; height: 5px; background: rgba(255,255,255,0.07); border-radius: 3px; overflow:hidden;">
                                <div id="brain-tier2-bar" style="height:100%; width:0%; background: #ffaa00; border-radius:3px; transition:width 0.7s ease;"></div>
                            </div>
                            <span id="brain-tier2-val" style="width: 30px; text-align:right; color: rgba(255,255,255,0.55); font-weight:700;">0/35</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 9px;">
                            <span style="width: 46px; color: rgba(255,255,255,0.4); font-weight: 700;">RISK</span>
                            <div style="flex:1; height: 5px; background: rgba(255,255,255,0.07); border-radius: 3px; overflow:hidden;">
                                <div id="brain-tier3-bar" style="height:100%; width:0%; background: #00cc88; border-radius:3px; transition:width 0.7s ease;"></div>
                            </div>
                            <span id="brain-tier3-val" style="width: 30px; text-align:right; color: rgba(255,255,255,0.55); font-weight:700;">0/15</span>
                        </div>
                    </div>
                    <!-- Threshold + block reason row -->
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-top:1px;">
                        <div style="font-size: 10px; color: rgba(255,255,255,0.35);">Threshold: <span id="brain-threshold-display" style="color: rgba(255,255,255,0.6); font-weight: 700;">55</span> pts</div>
                        <div id="brain-block-reason" style="font-size: 9px; font-weight: 700; color: rgba(255,255,255,0.25); letter-spacing: 0.5px;"></div>
                    </div>
                    <!-- Component micro-bars -->
                    <div id="brain-breakdown-bars" style="display: flex; flex-direction: column; gap: 3px; margin-top: 1px;">
                        <!-- Populated by JS -->
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Grid Layout -->
        <div class="dashboard-container">
            <!-- COLUMN 1: SENTIMENT GAUGE & INDICATORS PANEL -->
            <div id="sentiment-card-wrapper" style="display: contents;">
            <div class="card" id="sentiment-card" style="gap: 12px;">
                <div class="card-title">🧠 Tech Sentiment & Bias</div>
                
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                    <div class="sentiment-dial-box" id="dial-box-news">
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

                <div class="hide-on-fullscreen">
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

                <div class="bias-indicator" style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:10px; display:flex; flex-direction:column; gap:8px; font-size:12px;">
                    <div style="display:flex; justify-content:space-between; font-weight:700;">
                        <span style="color:var(--text-muted);">Resting Liquidity Pools</span>
                        <span style="color:var(--color-blue);" id="pool-count">0 Active</span>
                    </div>
                    <div id="liquidity-pools-container" style="display:flex; flex-direction:column; gap:6px; max-height:120px; overflow-y:auto; margin-top:2px;">
                        <span style="color:var(--text-muted); font-size:11px; text-align:center;">No active liquidity pools mapped.</span>
                    </div>
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
            </div>
            </div>

            <!-- COLUMN 2: CHARTING AREA & OPEN POSITIONS -->
            <div id="middle-column" style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">
                <div class="card" id="chart-card">
                    <!-- Fullscreen Top Bar (only visible when in fullscreen) -->
                    <div class="fullscreen-only-header" style="display: none; align-items: center; justify-content: space-between; padding: 10px 15px; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--glass-border); border-radius: 12px; gap: 20px;">
                        <div class="logo-section" style="display: flex; align-items: center;">
                            <h1 style="font-size: 18px; font-weight: 800; background: linear-gradient(135deg, #00f076, #00f0ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0; font-family: 'Outfit', sans-serif;">⚡ PULSE VIPER <span style="font-size: 10px; color: var(--color-blue); border: 1px solid var(--color-blue); padding: 1px 5px; border-radius: 3px; -webkit-text-fill-color: var(--color-blue); margin-left: 5px;">SMC EA</span></h1>
                        </div>
                        
                        <!-- Mirror tickers in fullscreen -->
                        <div style="flex: 1; display: flex; flex-direction: column; gap: 4px; overflow: hidden;">
                            <!-- Caution ticker mirror -->
                            <div class="ticker-row caution-ticker" style="background: rgba(255, 51, 102, 0.08); border: 1px solid rgba(255, 51, 102, 0.15); border-radius: 6px; height: 46px; line-height: 44px; font-size: 18px;">
                                <div class="ticker-header" style="padding: 0 12px; font-size: 14px; font-weight: 900;">⚠️ EDUCATIONAL PURPOSE</div>
                                <div class="ticker-wrap" id="fullscreen-caution-ticker-wrap">
                                    <span class="ticker-item">EDUCATIONAL PURPOSE ONLY • TRADE AT YOUR OWN RISK • THIS IS AN AUTOMATED AI-DRIVEN SMART MONEY CONCEPT (SMC) TRADING ALGORITHM • IT IDENTIFIES INSTITUTIONAL ORDER BLOCKS, FVGS, AND LIQUIDITY SWEEPS IN REAL-TIME • ALWAYS USE PROPER RISK MANAGEMENT</span>
                                </div>
                            </div>
                            <!-- News ticker mirror -->
                            <div id="fs-news-ticker-row" class="ticker-row news-ticker" style="background: rgba(0, 168, 255, 0.08); border: 1px solid rgba(0, 168, 255, 0.15); border-radius: 6px; height: 46px; line-height: 44px; font-size: 18px;">
                                <div class="ticker-header" style="padding: 0 12px; font-size: 14px; font-weight: 900;">📰 LIVE NEWS</div>
                                <div class="ticker-wrap" id="fullscreen-news-ticker-wrap">
                                    <span class="ticker-item" style="color: var(--text-muted);">No headlines loaded yet. Scraper starting...</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    
                    <!-- Main row to hold chart and sidebar -->
                    <div id="chart-main-row" style="display: flex; flex: 1; min-height: 0; width: 100%;">
                        
                        <!-- Left column for the chart itself -->
                        <div id="chart-left-col" style="display: flex; flex-direction: column; flex: 1; min-width: 0;">
                            
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
                        <div class="chart-tools" style="display: flex; align-items: center; gap: 8px;">
                            <div class="overlay-toggles" style="display: flex; align-items: center; gap: 6px; background: rgba(0, 0, 0, 0.3); border: 1px solid var(--glass-border); padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 700;">
                                <label style="display:flex; align-items:center; gap:3px; cursor:pointer; color:#00f076;" title="Toggle Long/Short Position Tool">
                                    <input type="checkbox" id="chk-overlay-pos" checked onchange="toggleChartOverlay('pos', this.checked)"> Position Tool
                                </label>
                                <label style="display:flex; align-items:center; gap:3px; cursor:pointer; color:#00f0ff;" title="Toggle High/Low Trendlines">
                                    <input type="checkbox" id="chk-overlay-trend" checked onchange="toggleChartOverlay('trend', this.checked)"> Trendlines
                                </label>
                                <label style="display:flex; align-items:center; gap:3px; cursor:pointer; color:#ffcc00;" title="Toggle Order Blocks & Volume Profile">
                                    <input type="checkbox" id="chk-overlay-ob" checked onchange="toggleChartOverlay('ob', this.checked)"> OBs / Volume
                                </label>
                            </div>
                            <button class="tool-btn" id="btn-tool-support" onclick="toggleDrawingMode('support')" title="Draw custom Support level on chart">Draw Support</button>
                            <button class="tool-btn" id="btn-tool-resistance" onclick="toggleDrawingMode('resistance')" title="Draw custom Resistance level on chart">Draw Resistance</button>
                            <button class="tool-btn" onclick="clearDrawings()" title="Clear drawing lines">Clear</button>
                            <button class="tool-btn" id="btn-tool-measure" onclick="toggleDrawingMode('measure')" title="Measure pips between two points on chart">Measure Pips</button>
                            <button class="tool-btn active" id="btn-tool-autoscroll" onclick="toggleAutoScroll()" title="Toggle auto-scroll to stay centered on new candles">Auto Scroll</button>
                            <button class="tool-btn" id="btn-tool-micro-scalp" onclick="toggleMicroScalpMode()" style="background: rgba(255, 204, 0, 0.15); color: #ffcc00; border: 1px solid rgba(255, 204, 0, 0.3);" title="Toggle Micro Scalp Mode ($3-$10 balance mode: 0.01 lot, 12p SL, 24p TP)">⚡ Micro Scalp Mode</button>
                            <button class="tool-btn" id="btn-tool-fullscreen" onclick="toggleFullScreen()" title="Toggle chart fullscreen">Full Screen</button>
                            <span id="candle-countdown" style="margin-left: 10px; font-weight: 700; color: #ff3366; background: rgba(255, 51, 102, 0.1); border: 1px solid rgba(255, 51, 102, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 11px; font-family: monospace; min-width: 90px; text-align: center; display: inline-block;">Candle: --:--</span>
                        </div>
                    </div>
                    <div class="chart-holder" style="background: rgba(0, 0, 0, 0.25); border-radius: 12px; border: 1px solid var(--glass-border); overflow: hidden; height: 450px; position: relative;">
                        <canvas id="canvas-chart" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: block; cursor: crosshair;"></canvas>
                        <!-- Active Position PnL Floating Card -->
                        <div class="card" id="fs-pnl-card" style="display: none; position: absolute; top: 15px; right: 60px; z-index: 100; min-width: 180px; background: rgba(10, 15, 25, 0.85); backdrop-filter: blur(10px); border: 1px solid var(--color-blue); padding: 12px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);">
                            <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; border: none; padding: 0; margin-bottom: 8px;">
                                <span style="font-size: 11px;">📈 Active Position PnL</span>
                                <span id="fs-pnl-action" style="font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 4px;">--</span>
                            </div>
                            <div style="font-size: 24px; font-weight: 800; text-align: center; margin-top: 5px; font-family: 'Outfit', sans-serif;" id="fs-pnl-value">
                                $0.00
                            </div>
                        </div>
                        <button id="btn-jump-latest" onclick="jumpToLatestTicks()" style="display:none; position:absolute; bottom:30px; right:85px; z-index:90; background:linear-gradient(135deg, #00f076, #00b894); color:#070a13; border:none; font-family:'Outfit',sans-serif; font-size:11px; font-weight:800; padding:6px 14px; border-radius:20px; cursor:pointer; box-shadow:0 4px 15px rgba(0,240,118,0.4); align-items:center; gap:6px; transition:transform 0.2s;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1.0)'" title="Jump to Latest Ticks">
                            <span>⬇ Jump to Latest Ticks</span>
                        </button>
                        <button id="btn-chart-fullscreen" onclick="toggleFullScreen()" style="position: absolute; top: 10px; right: 10px; background: rgba(0, 0, 0, 0.6); border: 1px solid rgba(255, 255, 255, 0.15); color: white; width: 36px; height: 36px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 16px; transition: all 0.2s ease; z-index: 10;" title="Toggle Fullscreen">⛶</button>
                    </div>
                        </div>
                        
                        <!-- Right column for indicators outside the chart -->
                        <div id="fullscreen-right-overlay" style="display: none; width: 280px; flex-direction: column; gap: 15px; padding-left: 15px; margin-left: 15px; border-left: 1px solid var(--glass-border); overflow-y: auto;">
                        </div>
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
                    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
                        <span>⏱️ History & Logs</span>
                        <div class="mode-selector" style="margin: 0; padding: 2px; border-radius: 6px;">
                            <button class="mode-btn active" id="btn-hist-daily" onclick="setHistoryFilter('daily')" style="padding: 4px 8px; font-size: 10px; border-radius: 4px; line-height: 1;">Daily</button>
                            <button class="mode-btn" id="btn-hist-weekly" onclick="setHistoryFilter('weekly')" style="padding: 4px 8px; font-size: 10px; border-radius: 4px; line-height: 1;">Weekly</button>
                        </div>
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Close Time</th>
                                    <th>Symbol</th>
                                    <th>Action</th>
                                    <th>Volume</th>
                                    <th>Entry</th>
                                    <th>Close Price</th>
                                    <th>Strategy</th>
                                    <th>Pattern</th>
                                    <th>Reason</th>
                                    <th>Outcome PnL</th>
                                </tr>
                            </thead>
                            <tbody id="history-body">
                                <tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No closed trades yet.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card" style="margin-top: 10px;">
                    <div class="card-title" style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
                        <span>📋 Live Execution Logs</span>
                        <span style="font-size: 8px; color: var(--text-muted); font-weight: 800; padding: 2px 6px; border-radius: 4px; background: rgba(0,240,118,0.1); color: var(--color-green); border: 1px solid rgba(0,240,118,0.2);">AUTO-UPDATING</span>
                    </div>
                    <div id="live-logs" style="background: rgba(0,0,0,0.4); border: 1px solid var(--glass-border); padding: 12px; border-radius: 8px; font-family: 'Consolas', 'Courier New', monospace; font-size: 10px; line-height: 1.4; color: #a9b7c6; height: 180px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;">Scanning for engine events...</div>
                </div>
            </div>

            <!-- COLUMN 3: SYSTEM PREDICTIONS & VOLUME ANALYTICS -->
            <div id="right-column" style="display: flex; flex-direction: column; gap: 20px; min-width: 0;">
                
                <!-- 🎯 Flagship Pure Price Action Engine Card -->
                <div class="card" id="price-action-engine-card">
                    <div class="card-title">🎯 Pure Price Action Execution Engine</div>
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <!-- Active Strategy Banner -->
                        <div style="background: rgba(0, 240, 118, 0.08); border: 1px solid rgba(0, 240, 118, 0.3); border-radius: 12px; padding: 14px; display: flex; flex-direction: column; gap: 6px; box-shadow: 0 4px 15px rgba(0, 240, 118, 0.08);">
                            <div style="font-size: 10px; color: var(--text-muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Active Strategy Engine</div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span id="pa-best-name" style="font-size: 20px; font-weight: 800; color: #00f076; text-shadow: 0 0 10px rgba(0,240,118,0.3);">QUANTUM VIPER</span>
                                <span style="font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 20px; background: rgba(0, 240, 118, 0.2); color: #00f076; border: 1px solid rgba(0, 240, 118, 0.4);">PURE PRICE ACTION</span>
                            </div>
                            <div style="font-size: 10px; color: var(--text-muted); line-height: 1.4; margin-top: 2px;">
                                100% Price Action Engine: Swing structure breakouts, pin-bar rejection wicks, volume expansion & choppiness whipsaw protection active.
                            </div>
                        </div>

                        <!-- Strategy Performance Metrics -->
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
                            <div style="background: rgba(0,0,0,0.15); padding: 8px; border-radius: 8px; border: 1px solid var(--glass-border); text-align: center;">
                                <div style="font-size: 9px; color: var(--text-muted);">Historical Accuracy</div>
                                <div style="font-size: 14px; font-weight: 800; color: var(--color-green); margin-top: 2px;">76.1%</div>
                            </div>
                            <div style="background: rgba(0,0,0,0.15); padding: 8px; border-radius: 8px; border: 1px solid var(--glass-border); text-align: center;">
                                <div style="font-size: 9px; color: var(--text-muted);">Profit Factor</div>
                                <div style="font-size: 14px; font-weight: 800; color: var(--color-gold); margin-top: 2px;">1.92</div>
                            </div>
                            <div style="background: rgba(0,0,0,0.15); padding: 8px; border-radius: 8px; border: 1px solid var(--glass-border); text-align: center;">
                                <div style="font-size: 9px; color: var(--text-muted);">Risk Geometry</div>
                                <div style="font-size: 14px; font-weight: 800; color: var(--color-blue); margin-top: 2px;">1:2.0 RR</div>
                            </div>
                        </div>

                        <!-- Price Action Rules Checklist -->
                        <div style="background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px solid var(--glass-border); padding: 10px; font-size: 10px; line-height: 1.5; color: var(--text-muted);">
                            <strong style="color: var(--text-primary);">⚡ Pure Price Action Rules:</strong><br>
                            • <strong>Swing Breakout</strong>: Body close beyond 20-bar high/low + Volume Expansion.<br>
                            • <strong>Pin-Bar Rejection</strong>: 58%+ Wick ratio at swing extremes.<br>
                            • <strong>Whipsaw Protection</strong>: CHOP Index >= 58.0 widens SL to 1.8x ATR.
                        </div>
                    </div>
                </div>

                <div id="volume-card-wrapper" style="display: contents;">
                <div class="card" id="volume-card">
                    <div class="card-title hide-on-fullscreen">📊 Volume Analytics</div>
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

                        <div class="hide-on-fullscreen">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 2px;">
                                <div style="font-size:11px; font-weight:600; color:var(--text-muted);">Volume Profile POC & Flow</div>
                                <div id="vp-market-control-badge" style="font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 4px; background: rgba(0, 240, 118, 0.15); color: var(--color-green); border: 1px solid rgba(0, 240, 118, 0.3);">BUYERS IN CONTROL 🟢</div>
                            </div>
                            <div class="vp-chart" id="vp-chart-container" style="display:flex; flex-direction:column; gap:3px; background:rgba(0,0,0,0.25); padding:8px; border-radius:10px; border:1px solid var(--glass-border); margin-top: 4px;">
                                <!-- Dynamic Content -->
                            </div>
                        </div>
                    </div>
                </div>
                </div>

                <!-- 📍 Key Technical Levels & SMC Structure Breakdown Card -->
                <div class="card" id="key-levels-breakdown-card">
                    <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
                        <span>📍 Key Levels & Structure Breakdown</span>
                        <span id="levels-symbol-badge" style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: rgba(59, 130, 246, 0.15); color: var(--color-blue); border: 1px solid rgba(59, 130, 246, 0.3);">XAUUSDm</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <!-- Primary Market Price Context Bar -->
                        <div style="background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); padding: 8px 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 11px; color: var(--text-muted); font-weight: 600;">CURRENT PRICE</span>
                            <span id="lvl-current-price" style="font-family: 'Outfit', sans-serif; font-size: 15px; font-weight: 800; color: #ffffff;">--</span>
                        </div>

                        <!-- Grid of Key Price Levels -->
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
                            <!-- Support -->
                            <div style="background: rgba(0, 240, 118, 0.05); border: 1px solid rgba(0, 240, 118, 0.2); border-radius: 8px; padding: 8px 10px;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 10px; font-weight: 700; color: var(--color-green);">SUPPORT</span>
                                    <span id="dist-support" style="font-size: 9px; color: var(--text-muted);">--</span>
                                </div>
                                <div id="val-support" style="font-size: 13px; font-weight: 800; color: var(--text-primary); margin-top: 3px;">--</div>
                                <div style="font-size: 8px; color: var(--text-muted); margin-top: 2px;">Key Price Floor Support</div>
                            </div>
                            <!-- Resistance -->
                            <div style="background: rgba(255, 51, 102, 0.05); border: 1px solid rgba(255, 51, 102, 0.2); border-radius: 8px; padding: 8px 10px;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 10px; font-weight: 700; color: var(--color-red);">RESISTANCE</span>
                                    <span id="dist-resistance" style="font-size: 9px; color: var(--text-muted);">--</span>
                                </div>
                                <div id="val-resistance" style="font-size: 13px; font-weight: 800; color: var(--text-primary); margin-top: 3px;">--</div>
                                <div style="font-size: 8px; color: var(--text-muted); margin-top: 2px;">Key Price Ceiling Resistance</div>
                            </div>
                            <!-- POC (Point of Control) -->
                            <div style="background: rgba(255, 204, 0, 0.05); border: 1px solid rgba(255, 204, 0, 0.2); border-radius: 8px; padding: 8px 10px;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span style="font-size: 10px; font-weight: 700; color: var(--color-gold);">POC</span>
                                    <span id="dist-poc" style="font-size: 9px; color: var(--text-muted);">--</span>
                                </div>
                                <div id="val-poc" style="font-size: 13px; font-weight: 800; color: var(--text-primary); margin-top: 3px;">--</div>
                                <div style="font-size: 8px; color: var(--text-muted); margin-top: 2px;">Highest Volume Magnet Level</div>
                            </div>
                            <!-- Previous Day Range (PDH / PDL) -->
                            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 8px 10px;">
                                <div style="font-size: 10px; font-weight: 700; color: var(--text-muted);">PDH / PDL</div>
                                <div id="val-pdh-pdl" style="font-size: 11px; font-weight: 800; color: var(--text-primary); margin-top: 3px;">-- / --</div>
                                <div style="font-size: 8px; color: var(--text-muted); margin-top: 2px;">Prev Day High & Low</div>
                            </div>
                            <!-- Previous Week Range (PWH / PWL) -->
                            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 8px 10px;">
                                <div style="font-size: 10px; font-weight: 700; color: var(--text-muted);">PWH / PWL</div>
                                <div id="val-pwh-pwl" style="font-size: 11px; font-weight: 800; color: var(--text-primary); margin-top: 3px;">-- / --</div>
                                <div style="font-size: 8px; color: var(--text-muted); margin-top: 2px;">Macro Weekly Pool Bounds</div>
                            </div>
                        </div>

                        <!-- Beginner Quick Guide Box -->
                        <div style="background: rgba(0, 240, 118, 0.05); border-left: 3px solid var(--color-green); padding: 10px 12px; border-radius: 0 8px 8px 0; font-size: 10px; line-height: 1.5; color: var(--text-muted); margin-top: 8px;">
                            <strong style="color: #00f076; font-weight: 800; font-size: 11px;">🌱 Beginner Guide (3 Easy Steps):</strong><br>
                            • <strong>1. Key Levels</strong>: <span style="color: #00f076; font-weight: 700;">SUPPORT</span> = Price Floor (Buy Zone), <span style="color: #ff3366; font-weight: 700;">RESISTANCE</span> = Price Ceiling (Sell Zone).<br>
                            • <strong>2. Yellow Line (POC)</strong>: Where buyers & sellers are trading heaviest right now.<br>
                            • <strong>3. Signal Lines</strong>: Look for neon <span style="color: #00f076;">🎯 ENTRY</span>, <span style="color: #ff3366;">🛑 SL</span>, and <span style="color: #00f076;">🎯 TP</span> lines on chart for automatic trade execution.
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">🎯 AI Trade Signal & Risk Plan</div>
                    <div class="prediction-box" id="pred-card">
                        <div class="pred-title" id="pred-action">SCANNING MARKET</div>
                        <div class="pred-row">
                            <span>Setup Strategy</span>
                            <span id="pred-type">Price Action</span>
                        </div>
                        <div class="pred-row">
                            <span>🎯 Entry Level</span>
                            <span id="pred-entry">--</span>
                        </div>
                        <div class="pred-row">
                            <span>🛡️ Max Risk (SL)</span>
                            <span id="pred-sl" style="color: var(--color-red);">--</span>
                        </div>
                        <div class="pred-row">
                            <span>🏆 Profit Goal (TP)</span>
                            <span id="pred-tp" style="color: var(--color-green);">--</span>
                        </div>
                        <div class="pred-row">
                            <span>📦 Safe Lot Size</span>
                            <span id="pred-lots">0.01</span>
                        </div>
                        <div class="pred-row">
                            <span>🤖 AI Confidence</span>
                            <span id="pred-confidence">—</span>
                        </div>
                        <div class="pred-row">
                            <span>🔮 Next Swing Target</span>
                            <span id="pred-next-swing" style="font-weight:700; color:var(--color-gold);">SCANNING SWING LEG ↗️</span>
                        </div>
                        <div class="pred-row">
                            <span>Market Structure Regime</span>
                            <span id="pred-regime">—</span>
                        </div>
                        <div class="pred-row">
                            <span>Active Sessions</span>
                            <span id="pred-sessions">—</span>
                        </div>
                        <div class="pred-row">
                            <span>VSA Patterns</span>
                            <span id="pred-vsa" style="font-weight:700; color:var(--text-muted);">—</span>
                        </div>
                        <div class="pred-row">
                            <span>⚡ Breakout Verification</span>
                            <span id="pred-breakout-type" style="font-weight:800; color:#00f076;">REAL BREAKOUT VERIFIED 🟢</span>
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
                        <!-- 🚀 1-Click Co-Pilot Stream Execution Button -->
                        <div style="margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px;">
                            <button id="btn-execute-copilot" onclick="executeCopilotTrade()" style="width: 100%; background: linear-gradient(135deg, #00f076, #00b894); border: none; color: #070a13; font-family: 'Outfit', sans-serif; font-size: 11px; font-weight: 800; padding: 10px 12px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 15px rgba(0, 240, 118, 0.3); transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1.0)'">
                                <span>🚀 EXECUTE CO-PILOT TRADE (1-CLICK MT5)</span>
                            </button>
                        </div>
                    </div>
                    
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        <div style="font-size:11px; font-weight:600; color:var(--text-muted);">Execution Skip Logs</div>
                        <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:6px;">
                            <div style="background:rgba(0,0,0,0.1); padding:6px; border-radius:6px; border:1px solid var(--glass-border); text-align:center;">
                                <div style="font-size:14px; font-weight:700; color:var(--color-red);" id="skip-spread">0</div>
                                <div style="font-size:9px; color:var(--text-muted);">High Spread</div>
                            </div>
                            <div style="background:rgba(0,0,0,0.1); padding:6px; border-radius:6px; border:1px solid var(--glass-border); text-align:center;">
                                <div style="font-size:14px; font-weight:700; color:var(--color-gold);" id="skip-news">0</div>
                                <div style="font-size:9px; color:var(--text-muted);">News Blocks</div>
                            </div>
                            <div style="background:rgba(0,0,0,0.1); padding:6px; border-radius:6px; border:1px solid rgba(100,80,255,0.4); text-align:center;">
                                <div style="font-size:14px; font-weight:700; color:#7b6dff;" id="skip-brain">0</div>
                                <div style="font-size:9px; color:var(--text-muted);">Brain Blocks</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">🕸️ Trade Starvation Analytics</div>
                    <div style="display:flex; flex-direction:column; gap:10px;">
                        <!-- Funnel stats -->
                        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:6px; background: rgba(0,0,0,0.15); padding: 8px; border-radius: 8px; border: 1px solid var(--glass-border); text-align:center;">
                            <div>
                                <div style="font-size:12px; font-weight:700; color:var(--color-blue);" id="starve-found">0</div>
                                <div style="font-size:8px; color:var(--text-muted); margin-top:2px;">Signals Found</div>
                            </div>
                            <div>
                                <div style="font-size:12px; font-weight:700; color:var(--color-red);" id="starve-blocked">0</div>
                                <div style="font-size:8px; color:var(--text-muted); margin-top:2px;">Blocked</div>
                            </div>
                            <div>
                                <div style="font-size:12px; font-weight:700; color:var(--color-green);" id="starve-executed">0</div>
                                <div style="font-size:8px; color:var(--text-muted); margin-top:2px;">Executed</div>
                            </div>
                            <div>
                                <div style="font-size:12px; font-weight:700; color:var(--color-gold);" id="starve-conv-rate">0.0%</div>
                                <div style="font-size:8px; color:var(--text-muted); margin-top:2px;">Conv. Rate</div>
                            </div>
                        </div>
                        
                        <!-- Top Blockers -->
                        <div style="display:flex; flex-direction:column; gap:6px;">
                            <div style="font-size:10px; font-weight:700; color:var(--text-muted);">Top System Blockers (Today)</div>
                            <div id="starve-blockers-list" style="display:flex; flex-direction:column; gap:4px;">
                                <span style="color:var(--text-muted); font-size:10px;">No signal blockages recorded today.</span>
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
                            <span>Safety Halt Status</span>
                            <span id="diag-safety-halt" style="color:var(--color-green); font-weight:700;">PASSED</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Daily P&L / Drawdown</span>
                            <span id="diag-daily-pnl" style="color:var(--text-primary); font-weight:700;">$0.00 (0.00%)</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Weekly P&L / Drawdown</span>
                            <span id="diag-weekly-pnl" style="color:var(--text-primary); font-weight:700;">$0.00 (0.00%)</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:4px;">
                            <span>Consecutive Losses</span>
                            <span id="diag-consec-losses" style="color:var(--text-primary); font-weight:700;">0</span>
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

            <!-- 🎓 Formal Legal Notice & Educational Disclaimer Card -->
            <div class="card" style="grid-column: 1 / -1; margin-top: 10px; background: rgba(13, 17, 26, 0.6); border: 1px solid var(--glass-border); border-radius: 12px; padding: 16px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #ffc107; font-weight: 800; font-size: 12px; letter-spacing: 0.5px;">
                    <span>🎓 LEGAL NOTICE & EDUCATIONAL DISCLAIMER</span>
                </div>
                <p style="font-size: 11px; line-height: 1.6; color: var(--text-muted); margin: 0;">
                    <strong>Educational & Research Purpose Only:</strong> PulseViper is designed exclusively as an educational research tool and quantitative market analysis framework. All technical indicators, Smart Money Concepts (SMC) zones, Volume Profile levels, and automated TradeBrain evaluations are provided solely for simulation, academic backtesting, and market structure study.<br>
                    <strong>No Financial Advice:</strong> Nothing contained within this software constitutes investment, financial, legal, or tax advice. Market predictions and algorithmic signals carry no profit guarantees.<br>
                    <strong>Independent Risk Acknowledgment:</strong> Trading foreign exchange (Forex), commodities, indices, cryptocurrencies, and financial derivatives carries a high level of risk and may not be suitable for all investors. You assume full responsibility and financial risk for any live or simulated order executions.
                </p>
            </div>
        </div>
    </div>

    <!-- ── Canvas Chart JavaScript Rendering engine ────── -->
    <script nonce="{{NONCE}}">
        // State manager to prevent settings flickering/blinking & race conditions
        const lastChangedTimes = {};
        function isSettingModifiedRecently(key) {
            return (Date.now() - (lastChangedTimes[key] || 0)) < 5000;
        }

        let lastSymbolChangeTime = 0;
        let lastSettingsChangeTime = 0;
        let historyFilter = 'daily';
        let cachedHistory = [];

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
            const hrs = Math.floor(remaining / 3600);
            const m = Math.floor((remaining % 3600) / 60);
            const s = remaining % 60;

            if (hrs > 0 || tfMinutes >= 60) {
                return `${hrs.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
            return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }

        function getSolidColor(colorStr) {
            if (!colorStr) return '#ffffff';
            if (colorStr.startsWith('rgba')) {
                const match = colorStr.match(new RegExp('rgba\\\\(\\\\s*(\\\\d+)\\\\s*,\\\\s*(\\\\d+)\\\\s*,\\\\s*(\\\\d+)\\\\s*,'));
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
                this.zoom = 6; // Smaller zoom shows more candles initially
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
                this.measureStart = null;
                this.autoScroll = true;
                this.showOverlayPos = true;
                this.showOverlayTrend = true;
                this.showOverlayOB = true;
                
                this.resize();
                window.addEventListener('resize', () => this.resize());
                
                this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
                this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
                this.canvas.addEventListener('mouseup', () => this.onMouseUp());
                this.canvas.addEventListener('mouseleave', () => { this.onMouseUp(); this.mouseX = null; this.mouseY = null; this.draw(); });
                this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
                this.canvas.addEventListener('click', (e) => this.onClick(e));
            }

            candleIndexToX(index) {
                if (index === null || index === undefined) return 0;
                const candleWidth = this.zoom;
                const totalWidth = candleWidth + 2;
                const rightOffset = Math.floor(this.offsetX / totalWidth);
                const rightMargin = 120; // MT5-style right margin/offset from price axis
                const baseWidth = this.width - 70 - rightMargin;
                return baseWidth - ((this.candles.length - 1 - index - rightOffset) * totalWidth) + this.offsetX % totalWidth + candleWidth / 2;
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
                
                const selectSymbolEl = document.getElementById('symbol-select');
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
                    const x = this.candleIndexToX(i);
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
                    const x = this.candleIndexToX(i);
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
            
            drawTrendlines(minPrice, maxPrice) {
                if (!this.candles || this.candles.length < 10) return;
                const len = this.candles.length;
                const startIndex = Math.max(0, len - 30);
                
                let highIdx1 = -1, highIdx2 = -1;
                let maxP1 = -Infinity, maxP2 = -Infinity;
                
                for (let i = startIndex; i < len - 5; i++) {
                    if (this.candles[i].high > maxP1) {
                        maxP1 = this.candles[i].high;
                        highIdx1 = i;
                    }
                }
                for (let i = len - 5; i < len; i++) {
                    if (this.candles[i].high > maxP2) {
                        maxP2 = this.candles[i].high;
                        highIdx2 = i;
                    }
                }
                
                if (highIdx1 >= 0 && highIdx2 > highIdx1) {
                    const x1 = this.candleIndexToX(highIdx1);
                    const y1 = this.priceToPixelY(maxP1, minPrice, maxPrice);
                    const x2 = this.candleIndexToX(highIdx2);
                    const y2 = this.priceToPixelY(maxP2, minPrice, maxPrice);
                    
                    this.ctx.save();
                    this.ctx.strokeStyle = 'rgba(0, 240, 255, 0.85)';
                    this.ctx.lineWidth = 1.5;
                    this.ctx.setLineDash([4, 2]);
                    this.ctx.beginPath();
                    this.ctx.moveTo(x1, y1);
                    this.ctx.lineTo(x2, y2);
                    this.ctx.stroke();
                    
                    const lastC = this.candles[len - 1];
                    if (lastC.close > maxP2) {
                        this.ctx.fillStyle = '#00f0ff';
                        this.ctx.font = 'bold 9px Outfit, sans-serif';
                        this.ctx.textAlign = 'left';
                        this.ctx.fillText('⚡ BREAKOUT ⬆', x2 + 5, y2 - 4);
                    }
                    this.ctx.restore();
                }
            }
            
            resize() {
                const rect = this.canvas.parentElement.getBoundingClientRect();
                const newWidth = Math.floor(rect.width);
                const newHeight = Math.floor(rect.height);
                
                // Only resize if logical dimensions have actually changed to prevent infinite layout feedback loops
                if (this.width === newWidth && this.height === newHeight) {
                    return;
                }
                
                const dpr = window.devicePixelRatio || 1;
                this.width = newWidth;
                this.height = newHeight;
                this.canvas.width = this.width * dpr;
                this.canvas.height = this.height * dpr;
                this.canvas.style.width = '100%';
                this.canvas.style.height = '100%';
                this.ctx.resetTransform();
                this.ctx.scale(dpr, dpr);
                this.draw();
            }
            
            setData(candles, levels, trades, fvgs, sweeps, mss_events) {
                this.candles = candles;
                this.levels = levels;
                this.trades = trades;
                this.fvgs = fvgs || [];
                this.sweeps = sweeps || [];
                this.mss_events = mss_events || [];
                if (this.autoScroll) {
                    this.offsetX = 0; // Keep chart centered on the last candle
                }
                this.draw();
            }
            
            onMouseDown(e) {
                if (chartDrawingMode) return;
                this.isDragging = true;
                this.startX = e.clientX;
                this.startY = e.clientY;
                this.startOffset = this.offsetX;
                this.startOffsetY = this.offsetY;
                // Disable auto-scroll when user interacts with chart
                if (this.autoScroll) {
                    this.autoScroll = false;
                    const btn = document.getElementById('btn-tool-autoscroll');
                    if (btn) {
                        btn.classList.remove('active');
                    }
                }
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
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;
                const price = this.pixelToPriceY(mouseY);
                const candleIdx = this.candleIndexFromX(mouseX);
                
                if (chartDrawingMode === 'measure') {
                    if (!this.measureStart) {
                        this.measureStart = { price, index: candleIdx, x: mouseX, y: mouseY };
                        this.draw();
                        return;
                    } else {
                        const start = this.measureStart;
                        this.measureStart = null;
                        
                        const diff = Math.abs(start.price - price);
                        const pips = diff * 10.0;
                        const bars = Math.abs(start.index - candleIdx);
                        
                        this.userLines.push({
                            type: 'measure',
                            priceStart: start.price,
                            priceEnd: price,
                            indexStart: start.index,
                            indexEnd: candleIdx,
                            color: '#ffc107',
                            title: `${diff.toFixed(2)} pts (${pips.toFixed(1)} pips) | ${bars} bars`
                        });
                        
                        toggleDrawingMode(null);
                        this.draw();
                        return;
                    }
                }
                
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
                this.measureStart = null;
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
                const rightMargin = 120;
                const baseWidth = this.width - 70 - rightMargin;
                
                const val = (baseWidth - x + this.offsetX % totalWidth + candleWidth / 2) / totalWidth;
                const index = Math.round(this.candles.length - 1 - rightOffset - val);
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
                    this.axisTagsToDraw = [];
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
                    const drawWidth = this.width - 70;
                    
                    // Draw watermark in background
                    this.drawWatermark();
                    const candleWidth = this.zoom;
                    const totalWidth = candleWidth + 2;
                    
                    const numVisible = Math.ceil(this.width / totalWidth);
                    const rightOffset = Math.floor(this.offsetX / totalWidth);
                    const startIndex = Math.max(0, this.candles.length - numVisible - rightOffset);
                    // Draw CRT and OB zones in the background (subtle outline borders only, no giant dark/green block fills)
                    if (this.levels && this.showOverlayOB) {
                        
                        // 1. CRT Zone (Clean Subtle Dotted Border Only)
                        if (this.levels.crt_high && this.levels.crt_low) {
                            const crtHighY = this.priceToPixelY(this.levels.crt_high, minPrice, maxPrice);
                            const crtLowY = this.priceToPixelY(this.levels.crt_low, minPrice, maxPrice);
                            this.ctx.save();
                            this.ctx.strokeStyle = 'rgba(168, 85, 247, 0.45)'; // Subtle purple border
                            this.ctx.lineWidth = 1;
                            this.ctx.setLineDash([4, 4]);
                            const yStart = Math.min(crtHighY, crtLowY);
                            const height = Math.abs(crtHighY - crtLowY);
                            this.ctx.strokeRect(0, yStart, drawWidth, height);

                            // Text Label for CRT Zone
                            this.ctx.fillStyle = 'rgba(168, 85, 247, 0.75)';
                            this.ctx.font = 'bold 9px Outfit, sans-serif';
                            this.ctx.textAlign = 'left';
                            this.ctx.fillText('CRT ZONE', 10, yStart + 12);
                            this.ctx.restore();
                        }
                        
                        // 2. Order Block Zone (Clean Subtle Dotted Border Only)
                        if (this.levels.ob_top && this.levels.ob_bottom) {
                            const obTopY = this.priceToPixelY(this.levels.ob_top, minPrice, maxPrice);
                            const obBottomY = this.priceToPixelY(this.levels.ob_bottom, minPrice, maxPrice);
                            const isBullish = this.levels.ob_direction === 'bullish';
                            this.ctx.save();
                            this.ctx.strokeStyle = isBullish ? 'rgba(0, 240, 118, 0.45)' : 'rgba(255, 51, 102, 0.45)';
                            this.ctx.lineWidth = 1;
                            this.ctx.setLineDash([4, 4]);
                            const yStart = Math.min(obTopY, obBottomY);
                            const height = Math.abs(obTopY - obBottomY);
                            this.ctx.strokeRect(0, yStart, drawWidth, height);

                            // Text Label for Order Block
                            this.ctx.fillStyle = isBullish ? 'rgba(0, 240, 118, 0.75)' : 'rgba(255, 51, 102, 0.75)';
                            this.ctx.font = 'bold 9px Outfit, sans-serif';
                            this.ctx.textAlign = 'left';
                            this.ctx.fillText(isBullish ? '+OB (BULLISH)' : '-OB (BEARISH)', 10, yStart + 12);
                            this.ctx.restore();
                        }
                    }
                        
                        // 3. Real-time Volume Profile rendering (recalculates dynamically on visible candles on every live tick)
                        const visibleCandles = this.getVisibleCandles();
                        if (visibleCandles && visibleCandles.length > 0) {
                            const numBins = 30;
                            let vMinP = minPrice;
                            let vMaxP = maxPrice;
                            if (vMaxP <= vMinP) vMaxP = vMinP + 1.0;
                            
                            const binStep = (vMaxP - vMinP) / numBins;
                            const binVols = new Array(numBins).fill(0);
                            const buyVols = new Array(numBins).fill(0);
                            const sellVols = new Array(numBins).fill(0);
                            
                            visibleCandles.forEach(c => {
                                const vol = c.volume || 1.0;
                                const cRange = c.high - c.low || 0.0001;
                                const buyRatio = Math.min(Math.max((c.close - c.low) / cRange, 0.0), 1.0);
                                const sellRatio = 1.0 - buyRatio;
                                
                                const midP = (c.high + c.low) / 2.0;
                                const binIdx = Math.min(Math.max(Math.floor((midP - vMinP) / binStep), 0), numBins - 1);
                                binVols[binIdx] += vol;
                                buyVols[binIdx] += vol * buyRatio;
                                sellVols[binIdx] += vol * sellRatio;
                            });
                            
                            let pocIdx = 0;
                            let maxBinVol = 0;
                            for (let k = 0; k < numBins; k++) {
                                if (binVols[k] > maxBinVol) {
                                    maxBinVol = binVols[k];
                                    pocIdx = k;
                                }
                            }
                            const maxBarWidth = Math.min(140, drawWidth * 0.15);
                            
                            this.ctx.save();
                            for (let k = 0; k < numBins; k++) {
                                const vol = binVols[k];
                                if (vol <= 0 || maxBinVol <= 0) continue;
                                
                                const binLow = vMinP + k * binStep;
                                const binHigh = binLow + binStep;
                                const yTop = this.priceToPixelY(binHigh, minPrice, maxPrice);
                                const yBottom = this.priceToPixelY(binLow, minPrice, maxPrice);
                                const yStart = Math.min(yTop, yBottom);
                                const height = Math.max(1, Math.abs(yTop - yBottom));
                                
                                const barWidth = (vol / maxBinVol) * maxBarWidth;
                                const bVol = buyVols[k];
                                const buyBarWidth = vol > 0 ? (bVol / vol) * barWidth : barWidth * 0.5;
                                const sellBarWidth = barWidth - buyBarWidth;
                                
                                const xStart = drawWidth - barWidth;
                                const xBuyEnd = xStart + buyBarWidth;
                                const isPoc = (k === pocIdx);
                                
                                // Draw Buyer portion (Emerald Green)
                                this.ctx.fillStyle = isPoc ? 'rgba(0, 240, 118, 0.75)' : 'rgba(0, 240, 118, 0.40)';
                                this.ctx.fillRect(xStart, yStart, buyBarWidth, height);
                                
                                // Draw Seller portion (Coral Red)
                                this.ctx.fillStyle = isPoc ? 'rgba(255, 51, 102, 0.75)' : 'rgba(255, 51, 102, 0.40)';
                                this.ctx.fillRect(xBuyEnd, yStart, sellBarWidth, height);
                                
                                // Outer border stroke
                                this.ctx.strokeStyle = isPoc ? '#ffcc00' : 'rgba(255, 255, 255, 0.15)';
                                this.ctx.lineWidth = isPoc ? 1.5 : 0.5;
                                this.ctx.strokeRect(xStart, yStart, barWidth, height);
                                
                                // Render POC Buyer/Seller Control Label on POC bar
                                if (isPoc) {
                                    const pocBuyPct = vol > 0 ? (bVol / vol) * 100.0 : 50.0;
                                    const isBuyPoc = pocBuyPct >= 50.0;
                                    this.ctx.fillStyle = isBuyPoc ? '#00f076' : '#ff3366';
                                    this.ctx.font = 'bold 9px Outfit, sans-serif';
                                    this.ctx.textAlign = 'right';
                                    this.ctx.fillText(`POC: ${isBuyPoc ? 'BUYERS 🟢' : 'SELLERS 🔴'} (${pocBuyPct.toFixed(0)}%)`, xStart - 6, yStart + height / 2 + 3);
                                }
                            }
                            this.ctx.restore();
                        }
                    
                    // 4. Fair Value Gaps (Disabled per user request for ultra-clean chart)
                    // FVG boxes omitted to prevent chart visual cluttering
                    
                    // Draw candles
                    for (let i = startIndex; i < this.candles.length; i++) {
                        const candle = this.candles[i];
                        const x = this.candleIndexToX(i) - candleWidth / 2;
                        
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
                    
                    if (this.showOverlayTrend) {
                        this.drawTrendlines(minPrice, maxPrice);
                    }
                    
                    // Draw sweeps
                    if (this.sweeps && this.sweeps.length > 0) {
                        this.sweeps.forEach(sweep => {
                            if (sweep.index < 0 || sweep.index >= this.candles.length) return;
                            const candle = this.candles[sweep.index];
                            const x = this.candleIndexToX(sweep.index);
                            if (x < 0 || x > this.width - 70) return;
                            
                            const isBullish = sweep.type === 'bullish';
                            const priceY = isBullish ? 
                                this.priceToPixelY(candle.low, minPrice, maxPrice) : 
                                this.priceToPixelY(candle.high, minPrice, maxPrice);
                                
                            this.ctx.save();
                            this.ctx.fillStyle = isBullish ? '#00f0ff' : '#ff007f';
                            this.ctx.font = 'bold 8px Outfit, sans-serif';
                            this.ctx.textAlign = 'center';
                            
                            if (isBullish) {
                                this.ctx.fillText('▲ SWEEP', x, priceY + 12);
                                const sweptY = this.priceToPixelY(sweep.price, minPrice, maxPrice);
                                this.ctx.fillStyle = 'rgba(0, 240, 255, 0.6)';
                                this.ctx.beginPath();
                                this.ctx.arc(x, sweptY, 2.5, 0, 2 * Math.PI);
                                this.ctx.fill();
                            } else {
                                this.ctx.fillText('▼ SWEEP', x, priceY - 6);
                                const sweptY = this.priceToPixelY(sweep.price, minPrice, maxPrice);
                                this.ctx.fillStyle = 'rgba(255, 0, 127, 0.6)';
                                this.ctx.beginPath();
                                this.ctx.arc(x, sweptY, 2.5, 0, 2 * Math.PI);
                                this.ctx.fill();
                            }
                            this.ctx.restore();
                        });
                    }
                    
                    // Draw MSS Events
                    if (this.mss_events && this.mss_events.length > 0) {
                        this.mss_events.forEach(mss => {
                            if (mss.index < 0 || mss.index >= this.candles.length) return;
                            const x = this.candleIndexToX(mss.index);
                            if (x < 0 || x > this.width - 70) return;
                            
                            const isBullish = mss.type === 'bullish';
                            this.ctx.save();
                            this.ctx.strokeStyle = isBullish ? 'rgba(0, 240, 118, 0.35)' : 'rgba(255, 51, 102, 0.35)';
                            this.ctx.lineWidth = 1.25;
                            this.ctx.setLineDash([3, 3]);
                            
                            this.ctx.beginPath();
                            this.ctx.moveTo(x, 20);
                            this.ctx.lineTo(x, this.height - 25);
                            this.ctx.stroke();
                            
                            this.ctx.fillStyle = isBullish ? '#00f076' : '#ff3366';
                            this.ctx.font = 'bold 8px Outfit, sans-serif';
                            this.ctx.textAlign = 'center';
                            const labelY = isBullish ? 35 : this.height - 40;
                            this.ctx.fillText(isBullish ? '▲ MSS' : '▼ MSS', x, labelY);
                            this.ctx.restore();
                        });
                    }

                    // Draw Trend Ribbon (EMA Expansion)
                    this.drawEMAs(minPrice, maxPrice);
                    
                    // 1. Draw solid background bars for axes BEFORE indicators & price tags
                    this.drawPriceAxisBackground();
                    this.drawTimeAxisBackground();
                    
                    // 2. Draw price ticks on top of backgrounds
                    this.drawPriceAxisTicks(minPrice, maxPrice);
                    this.drawTimeAxisTicks();
                    
                    // 3. Draw clean key indicator lines (Support, Resistance, POC, PDH, PDL, PWH, PWL, Entry, TP, SL, Signals)
                    if (this.levels) {
                        if (this.levels.support) this.drawHorizontalLine(this.levels.support, 'rgba(0, 240, 118, 0.75)', 'SUPPORT', minPrice, maxPrice, false, 1, [4, 4]);
                        if (this.levels.resistance) this.drawHorizontalLine(this.levels.resistance, 'rgba(255, 51, 102, 0.75)', 'RESISTANCE', minPrice, maxPrice, false, 1, [4, 4]);
                        if (this.levels.poc) this.drawHorizontalLine(this.levels.poc, 'rgba(255, 204, 0, 0.75)', 'POC', minPrice, maxPrice, false, 1, [4, 4]);
                        if (this.levels.pdh) this.drawHorizontalLine(this.levels.pdh, 'rgba(241, 245, 249, 0.8)', 'PDH', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pdl) this.drawHorizontalLine(this.levels.pdl, 'rgba(241, 245, 249, 0.8)', 'PDL', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pwh) this.drawHorizontalLine(this.levels.pwh, 'rgba(216, 180, 254, 0.8)', 'PWH', minPrice, maxPrice, false, 1, [3, 3]);
                        if (this.levels.pwl) this.drawHorizontalLine(this.levels.pwl, 'rgba(216, 180, 254, 0.8)', 'PWL', minPrice, maxPrice, false, 1, [3, 3]);
                        // 3. Target Setup & Active Position Shaded Zones (TradingView Position Tool Style)
                        const setupEntry = this.levels.entry_price;
                        const setupSL = this.levels.sl_price;
                        const setupTP = this.levels.tp_price;
                        const setupAct = (this.levels.entry_action || 'BUY').toUpperCase();
                        
                        if (setupEntry && (setupSL || setupTP) && this.showOverlayPos) {
                            const entryY = this.priceToPixelY(setupEntry, minPrice, maxPrice);
                            const slY = setupSL ? this.priceToPixelY(setupSL, minPrice, maxPrice) : null;
                            const tpY = setupTP ? this.priceToPixelY(setupTP, minPrice, maxPrice) : null;
                            const drawWidth = this.width - 70;
                            const posBoxX = Math.max(0, drawWidth - 260);
                            const posBoxW = drawWidth - posBoxX;

                            // Take Profit Zone (Emerald Green)
                            if (tpY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = 'rgba(0, 240, 118, 0.12)';
                                this.ctx.strokeStyle = 'rgba(0, 240, 118, 0.40)';
                                this.ctx.lineWidth = 1;
                                const yStart = Math.min(entryY, tpY);
                                const height = Math.abs(entryY - tpY);
                                this.ctx.fillRect(posBoxX, yStart, posBoxW, height);
                                this.ctx.strokeRect(posBoxX, yStart, posBoxW, height);
                                
                                const tpPips = (Math.abs(setupTP - setupEntry) * 10.0).toFixed(1);
                                this.ctx.fillStyle = '#00f076';
                                this.ctx.font = 'bold 10px Outfit, sans-serif';
                                this.ctx.textAlign = 'right';
                                this.ctx.fillText(`🎯 TP: ${this.formatPrice(setupTP)} (+${tpPips} pips)`, drawWidth - 15, yStart + 14);
                                this.ctx.restore();
                            }

                            // Stop Loss Zone (Coral Red)
                            if (slY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = 'rgba(255, 51, 102, 0.12)';
                                this.ctx.strokeStyle = 'rgba(255, 51, 102, 0.40)';
                                this.ctx.lineWidth = 1;
                                const yStart = Math.min(entryY, slY);
                                const height = Math.abs(entryY - slY);
                                this.ctx.fillRect(posBoxX, yStart, posBoxW, height);
                                this.ctx.strokeRect(posBoxX, yStart, posBoxW, height);

                                const slPips = (Math.abs(setupEntry - setupSL) * 10.0).toFixed(1);
                                this.ctx.fillStyle = '#ff3366';
                                this.ctx.font = 'bold 10px Outfit, sans-serif';
                                this.ctx.textAlign = 'right';
                                this.ctx.fillText(`🛑 SL: ${this.formatPrice(setupSL)} (-${slPips} pips)`, drawWidth - 15, yStart + height - 6);
                                this.ctx.restore();
                            }

                            // TradingView R:R Ratio Badge Tool removed as requested

                            const entryColor = setupAct === 'BUY' ? '#00f076' : (setupAct === 'SELL' ? '#ff3366' : '#00f0ff');
                            this.drawHorizontalLine(setupEntry, entryColor, `🎯 ${setupAct} ENTRY`, minPrice, maxPrice, true, 2, null, true, true);
                            if (setupSL) this.drawHorizontalLine(setupSL, '#ff3366', '🛑 TARGET SL', minPrice, maxPrice, true, 1.5, [2, 2], true, true);
                            if (setupTP) this.drawHorizontalLine(setupTP, '#00f076', '🎯 TARGET TP', minPrice, maxPrice, true, 1.5, [2, 2], true, true);
                        }
                    }
                    
                    if (this.trades && this.showOverlayPos) {
                        this.trades.forEach(t => {
                            const entryY = this.priceToPixelY(t.entry, minPrice, maxPrice);
                            const slY = t.sl ? this.priceToPixelY(t.sl, minPrice, maxPrice) : null;
                            const tpY = t.tp ? this.priceToPixelY(t.tp, minPrice, maxPrice) : null;
                            
                            const drawWidth = this.width - 70;
                            const posBoxX = Math.max(0, drawWidth - 260);
                            const posBoxW = drawWidth - posBoxX;
                            
                            // Draw transparent position visual zones (like TradingView's position tools)
                            if (tpY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = t.action === 'BUY' ? 'rgba(0, 240, 118, 0.15)' : 'rgba(255, 51, 102, 0.15)';
                                const yStart = Math.min(entryY, tpY);
                                const height = Math.abs(entryY - tpY);
                                this.ctx.fillRect(posBoxX, yStart, posBoxW, height);
                                this.ctx.restore();
                            }
                            
                            if (slY !== null && entryY >= 0 && entryY <= this.height - 25) {
                                this.ctx.save();
                                this.ctx.fillStyle = t.action === 'BUY' ? 'rgba(255, 51, 102, 0.15)' : 'rgba(0, 240, 118, 0.15)';
                                const yStart = Math.min(entryY, slY);
                                const height = Math.abs(entryY - slY);
                                this.ctx.fillRect(0, yStart, drawWidth, height);
                                this.ctx.restore();
                            }
                            
                            if (t.entry) this.drawHorizontalLine(t.entry, '#00a8ff', `${t.action} ENTRY`, minPrice, maxPrice, true, 2);
                            if (t.sl) this.drawHorizontalLine(t.sl, '#ff3366', 'STOP LOSS', minPrice, maxPrice, true, 2);
                            if (t.tp) this.drawHorizontalLine(t.tp, '#00f076', 'TAKE PROFIT', minPrice, maxPrice, true, 2);
                        });
                    }
                    
                    this.userLines.forEach(line => {
                        if (line.type === 'measure') {
                            const xStart = this.candleIndexToX(line.indexStart);
                            const xEnd = this.candleIndexToX(line.indexEnd);
                            const yStart = this.priceToPixelY(line.priceStart, minPrice, maxPrice);
                            const yEnd = this.priceToPixelY(line.priceEnd, minPrice, maxPrice);
                            
                            this.ctx.save();
                            this.ctx.strokeStyle = line.color;
                            this.ctx.lineWidth = 1;
                            this.ctx.setLineDash([3, 3]);
                            this.ctx.strokeRect(xStart, yStart, xEnd - xStart, yEnd - yStart);
                            this.ctx.fillStyle = 'rgba(255, 193, 7, 0.08)';
                            this.ctx.fillRect(xStart, yStart, xEnd - xStart, yEnd - yStart);
                            
                            this.ctx.fillStyle = '#ffc107';
                            this.ctx.font = 'bold 9px monospace';
                            this.ctx.textAlign = 'center';
                            const labelX = (xStart + xEnd) / 2;
                            const labelY = Math.min(yStart, yEnd) - 5;
                            this.ctx.fillText(line.title, labelX, labelY);
                            this.ctx.restore();
                        } else {
                            this.drawHorizontalLine(line.price, line.color, line.title, minPrice, maxPrice, false, 2);
                        }
                    });
                    
                    // Live measurement ruler preview
                    if (chartDrawingMode === 'measure' && this.measureStart && this.mouseX !== null && this.mouseY !== null) {
                        const xStart = this.candleIndexToX(this.measureStart.index);
                        const yStart = this.priceToPixelY(this.measureStart.price, minPrice, maxPrice);
                        const xEnd = this.mouseX;
                        const yEnd = this.mouseY;
                        const priceEnd = this.pixelToPriceY(yEnd);
                        const candleIdxEnd = this.candleIndexFromX(xEnd);
                        
                        const diff = Math.abs(this.measureStart.price - priceEnd);
                        const pips = diff * 10.0;
                        const bars = Math.abs(this.measureStart.index - candleIdxEnd);
                        const title = `${diff.toFixed(2)} pts (${pips.toFixed(1)} pips) | ${bars} bars`;
                        
                        this.ctx.save();
                        this.ctx.strokeStyle = '#ffc107';
                        this.ctx.lineWidth = 1;
                        this.ctx.setLineDash([3, 3]);
                        this.ctx.strokeRect(xStart, yStart, xEnd - xStart, yEnd - yStart);
                        this.ctx.fillStyle = 'rgba(255, 193, 7, 0.04)';
                        this.ctx.fillRect(xStart, yStart, xEnd - xStart, yEnd - yStart);
                        
                        this.ctx.fillStyle = '#ffc107';
                        this.ctx.font = 'bold 9px monospace';
                        this.ctx.textAlign = 'center';
                        const labelX = (xStart + xEnd) / 2;
                        const labelY = Math.min(yStart, yEnd) - 5;
                        this.ctx.fillText(title, labelX, labelY);
                        this.ctx.restore();
                    }
                    
                    // Draw live Bid/Ask tracking lines
                    const currentBid = this.bidPrice || (this.candles.length > 0 ? this.candles[this.candles.length - 1].close : 0);
                    const currentAsk = this.askPrice || currentBid;
                    if (currentBid) {
                        this.drawHorizontalLine(currentBid, 'rgba(255, 165, 0, 0.85)', 'BID', minPrice, maxPrice, false, 1.5, [3, 3]);
                    }
                    if (currentAsk) {
                        this.drawHorizontalLine(currentAsk, 'rgba(0, 210, 211, 0.85)', 'ASK', minPrice, maxPrice, false, 1.5, [3, 3]);
                    }
                    
                    // Draw decluttered right price axis tags without vertical overlap
                    this.drawDeclutteredAxisTags(minPrice, maxPrice);

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

            drawEMAs(minPrice, maxPrice) {
                if (!this.candles || this.candles.length < 5) return;
                const drawWidth = this.width - 70;
                
                const period = 14;
                const k = 2 / (period + 1);
                let ema = this.candles[0].close;
                const emaValues = [ema];
                for (let i = 1; i < this.candles.length; i++) {
                    ema = (this.candles[i].close * k) + (ema * (1 - k));
                    emaValues.push(ema);
                }

                this.ctx.save();
                this.ctx.lineWidth = 2.5;
                this.ctx.lineCap = 'round';
                this.ctx.lineJoin = 'round';

                for (let i = 1; i < this.candles.length; i++) {
                    const x1 = this.candleIndexToX(i - 1);
                    const x2 = this.candleIndexToX(i);
                    if (x2 < 0 || x1 > drawWidth) continue;

                    const y1 = this.priceToPixelY(emaValues[i - 1], minPrice, maxPrice);
                    const y2 = this.priceToPixelY(emaValues[i], minPrice, maxPrice);
                    const isBullish = this.candles[i].close >= emaValues[i];

                    this.ctx.strokeStyle = isBullish ? '#00e676' : '#ff1744';
                    this.ctx.beginPath();
                    this.ctx.moveTo(x1, y1);
                    this.ctx.lineTo(x2, y2);
                    this.ctx.stroke();
                }
                this.ctx.restore();
            }

            drawTrendlines(minPrice, maxPrice) {
                // Additional trendline overlay
            }
            
            drawHorizontalLine(price, color, label, minPrice, maxPrice, isSolid = true, lineWidth = 1, dashPattern = null, drawAxisTag = true, hideLeftLabel = false) {
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
                
                // Draw label above line ONLY if not hidden by position tool overlay
                if (!hideLeftLabel) {
                    this.ctx.fillStyle = solidColor;
                    this.ctx.font = 'bold 10px Outfit, sans-serif';
                    this.ctx.textAlign = 'left';
                    this.ctx.fillText(`${label}`, 10, y - 4);
                }
 
                // Queue tag for decluttered price axis rendering
                if (drawAxisTag) {
                    if (!this.axisTagsToDraw) this.axisTagsToDraw = [];
                    this.axisTagsToDraw.push({ price, color, label, y });
                }
            }

            drawDeclutteredAxisTags(minPrice, maxPrice) {
                if (!this.axisTagsToDraw || this.axisTagsToDraw.length === 0) return;

                const tags = this.axisTagsToDraw
                    .filter(t => t.y >= 0 && t.y <= this.height - 25)
                    .map(t => ({
                        price: t.price,
                        color: t.color,
                        label: t.label,
                        solidColor: getSolidColor(t.color),
                        targetY: t.y,
                        adjustedY: t.y
                    }));

                if (tags.length === 0) return;

                // Sort ascending by y (top to bottom)
                tags.sort((a, b) => a.targetY - b.targetY);

                // Vertical anti-collision staggering (minimum 16px vertical gap)
                const minGap = 16;
                for (let i = 1; i < tags.length; i++) {
                    const prev = tags[i - 1];
                    const curr = tags[i];
                    if (curr.adjustedY < prev.adjustedY + minGap) {
                        curr.adjustedY = prev.adjustedY + minGap;
                    }
                }

                // Clamp to canvas height bounds
                const maxAllowedY = this.height - 30;
                if (tags[tags.length - 1].adjustedY > maxAllowedY) {
                    tags[tags.length - 1].adjustedY = maxAllowedY;
                    for (let i = tags.length - 2; i >= 0; i--) {
                        if (tags[i].adjustedY > tags[i + 1].adjustedY - minGap) {
                            tags[i].adjustedY = tags[i + 1].adjustedY - minGap;
                        }
                    }
                }

                // Render tags on right axis
                const axisX = this.width - 68;
                const axisW = 66;
                const tagH = 15;

                tags.forEach(t => {
                    const tagY = t.adjustedY;
                    const origY = t.targetY;
                    const priceText = this.formatPrice(t.price);

                    this.ctx.save();
                    
                    // Draw dashed connector line tick if tag was shifted by staggering
                    if (Math.abs(tagY - origY) > 2) {
                        this.ctx.strokeStyle = t.solidColor;
                        this.ctx.lineWidth = 1;
                        this.ctx.setLineDash([2, 2]);
                        this.ctx.beginPath();
                        this.ctx.moveTo(this.width - 70, origY);
                        this.ctx.lineTo(axisX, tagY);
                        this.ctx.stroke();
                    }

                    // Dark pill badge background
                    const rectY = tagY - tagH / 2;
                    this.ctx.fillStyle = '#0b0f19';
                    this.ctx.beginPath();
                    if (this.ctx.roundRect) {
                        this.ctx.roundRect(axisX, rectY, axisW, tagH, 3);
                    } else {
                        this.ctx.rect(axisX, rectY, axisW, tagH);
                    }
                    this.ctx.fill();

                    // Left color accent bar
                    this.ctx.fillStyle = t.solidColor;
                    this.ctx.fillRect(axisX, rectY, 3, tagH);

                    // Pill border
                    this.ctx.strokeStyle = t.solidColor;
                    this.ctx.lineWidth = 1;
                    this.ctx.setLineDash([]);
                    if (this.ctx.roundRect) {
                        this.ctx.stroke();
                    } else {
                        this.ctx.strokeRect(axisX, rectY, axisW, tagH);
                    }

                    // Price text inside badge
                    this.ctx.fillStyle = t.label.startsWith('BID') || t.label.startsWith('ASK') ? t.solidColor : '#ffffff';
                    this.ctx.font = 'bold 9px monospace';
                    this.ctx.textAlign = 'center';
                    this.ctx.fillText(priceText, axisX + axisW / 2 + 1, tagY + 3);
                    this.ctx.restore();

                    // Draw BID countdown badge if BID line
                    if (t.label.startsWith('BID')) {
                        const countdownStr = typeof getCountdownTime === 'function' ? getCountdownTime() : '00:00';
                        this.ctx.save();
                        this.ctx.fillStyle = 'rgba(255, 71, 87, 0.2)';
                        this.ctx.strokeStyle = '#ff4757';
                        this.ctx.lineWidth = 1;
                        
                        const badgeWidth = 42;
                        const badgeX = this.width - 70 - badgeWidth - 4;
                        const badgeY = origY - 8;
                        const badgeHeight = 16;
                        
                        this.ctx.fillRect(badgeX, badgeY, badgeWidth, badgeHeight);
                        this.ctx.strokeRect(badgeX, badgeY, badgeWidth, badgeHeight);
                        
                        this.ctx.fillStyle = '#ff4757';
                        this.ctx.font = 'bold 9px monospace';
                        this.ctx.textAlign = 'center';
                        this.ctx.fillText(countdownStr, badgeX + badgeWidth / 2, badgeY + 11);
                        this.ctx.restore();
                    }
                });
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

        window.CanvasChart = CanvasChart;
        window.Chart = CanvasChart;

        let canvasChart = null;
        let chart = null;
        let activeTimeframe = localStorage.getItem('pulse_viper_active_timeframe') || 'M5';
        let chartDrawingMode = null;

        // Auto-detect and configure backend API base URL (with safe localStorage fallback)
        let apiBase = '';
        try {
            apiBase = localStorage.getItem('pulse_viper_api_url') || '';
            if (apiBase && window.location.port && window.location.protocol !== 'file:' && !apiBase.includes(window.location.port)) {
                apiBase = '';
            }
        } catch (e) {
            console.warn("localStorage access blocked:", e);
        }

        if (!apiBase) {
            if (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '8000')) {
                apiBase = 'http://localhost:8000';
            } else {
                apiBase = window.location.origin;
            }
        }

        function initDashboard() {
            canvasChart = new CanvasChart('canvas-chart');
            chart = canvasChart;
            window.canvasChart = canvasChart;
            window.chart = canvasChart;

            // Handle fullscreen changes to resize chart
            document.addEventListener('fullscreenchange', () => {
                if (canvasChart) {
                    canvasChart.resize();
                }
            });

            // Resize observer to handle container size changes
            const chartHolder = document.querySelector('.chart-holder');
            if (chartHolder && canvasChart) {
                const resizeObserver = new ResizeObserver(() => {
                    window.requestAnimationFrame(() => {
                        if (canvasChart) {
                            canvasChart.resize();
                        }
                    });
                });
                resizeObserver.observe(chartHolder);
            }
            
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
                
                // Candle Countdown
                const countdownEl = document.getElementById('candle-countdown');
                if (countdownEl) {
                    const tf = typeof activeTimeframe !== 'undefined' ? activeTimeframe : 'M5';
                    countdownEl.innerText = `${tf}: ${getCountdownTime()}`;
                }
            }
            updateClocks();
            
            // Set initial active timeframe visual state
            document.querySelectorAll('.tf-btn').forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.getElementById(`btn-tf-${activeTimeframe.toLowerCase()}`);
            if (activeBtn) activeBtn.classList.add('active');
            setInterval(updateClocks, 1000);

            // Fetch status FIRST to populate the symbol dropdown with real symbols from the backend,
            // then fetch chart data with the correct symbol on the initial load
            fetchStatus().then(() => {
                fetchChartData();
            }).catch(() => {
                fetchChartData(); // still try even if status fetch fails
            });
            fetchLogs();
            // Fetch Status every 2000ms for regular updates
            setInterval(fetchStatus, 2000);
            // Fetch Chart every 5000ms for smooth transitions
            setInterval(fetchChartData, 5000);
            setInterval(fetchLogs, 5000);

            // Dynamically bind interactive controls to satisfy strict CSP
            bindInteractiveElements();
        }

        // Bind all interactive elements dynamically to comply with strict CSP (no inline events allowed)
        function bindInteractiveElements() {
            // Symbol selection dropdown
            const symbolSelect = document.getElementById('symbol-select');
            if (symbolSelect) {
                symbolSelect.addEventListener('change', (e) => changeSymbol(e.target.value));
            }

            // Add Custom Symbol button
            const addSymbolBtn = document.getElementById('btn-add-custom-symbol');
            if (addSymbolBtn) {
                addSymbolBtn.addEventListener('click', addCustomSymbol);
            }

            // Drawer toggle
            const gearBtn = document.getElementById('gear-toggle-btn');
            if (gearBtn) gearBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); toggleConfigDrawer(); };

            const overlay = document.getElementById('config-overlay');
            if (overlay) overlay.onclick = (e) => { e.preventDefault(); e.stopPropagation(); toggleConfigDrawer(false); };

            const drawerClose = document.querySelector('.drawer-close');
            if (drawerClose) drawerClose.onclick = (e) => { e.preventDefault(); e.stopPropagation(); toggleConfigDrawer(false); };

            // Trading Mode buttons
            const modeBtns = {
                'btn-mode-scalping': 'scalping',
                'btn-mode-intraday': 'intraday',
                'btn-mode-swing': 'swing'
            };
            for (const [id, mode] of Object.entries(modeBtns)) {
                const el = document.getElementById(id);
                if (el) {
                    el.addEventListener('click', () => setTradingMode(mode));
                }
            }

            // Timeframe buttons
            const tfButtons = ['m1', 'm5', 'm15', 'm30', 'h1', 'h4', 'd1'];
            tfButtons.forEach(tf => {
                const el = document.getElementById(`btn-tf-${tf}`);
                if (el) {
                    el.addEventListener('click', () => window.setTimeframe(tf.toUpperCase()));
                }
            });

            // Checkbox settings switches
            const switches = {
                'toggle-autotrade': 'auto_trade_enabled',
                'toggle-paper': 'paper_mode',
                'toggle-compounding': 'compounding_mode',
                'toggle-hedging': 'hedging_mode',
                'toggle-trailing': 'trailing_stop_enabled',
                'toggle-breakeven': 'break_even_enabled',
                'toggle-news-filter': 'news_filter_enabled',
                'toggle-self-learning': 'self_learning_filter',
                'toggle-strict-mode': 'strict_mode',
                'toggle-dynamic-risk': 'dynamic_risk_enabled',
                'toggle-regime-filter': 'dynamic_regime_filter',
                'toggle-manual-lot': 'use_manual_lot'
            };
            for (const [id, key] of Object.entries(switches)) {
                const el = document.getElementById(id);
                if (el) {
                    el.addEventListener('change', () => toggleSetting(key));
                }
            }

            // Sliders & Range inputs
            const riskInput = document.getElementById('input-risk');
            if (riskInput) {
                riskInput.addEventListener('input', (e) => updateRiskValue(e.target.value));
                riskInput.addEventListener('change', (e) => saveRiskSetting(e.target.value));
            }

            const manualLotInput = document.getElementById('input-manual-lot');
            if (manualLotInput) {
                manualLotInput.addEventListener('input', (e) => updateManualLotValue(e.target.value));
                manualLotInput.addEventListener('change', (e) => saveManualLotSetting(e.target.value));
            }
            const manualLotNum = document.getElementById('input-manual-lot-num');
            if (manualLotNum) {
                manualLotNum.addEventListener('input', (e) => updateManualLotValue(e.target.value));
                manualLotNum.addEventListener('change', (e) => saveManualLotSetting(e.target.value));
            }

            const minAiConfInput = document.getElementById('input-min-ai-conf');
            if (minAiConfInput) {
                minAiConfInput.addEventListener('input', (e) => updateMinAIConfValue(e.target.value));
                minAiConfInput.addEventListener('change', (e) => saveMinAIConfSetting(e.target.value));
            }

            const maxDailyInput = document.getElementById('input-max-daily');
            if (maxDailyInput) {
                maxDailyInput.addEventListener('input', (e) => updateMaxDailyValue(e.target.value));
                maxDailyInput.addEventListener('change', (e) => saveMaxDailySetting(e.target.value));
            }

            const maxSpreadInput = document.getElementById('input-max-spread');
            if (maxSpreadInput) {
                maxSpreadInput.addEventListener('input', (e) => updateMaxSpreadValue(e.target.value));
                maxSpreadInput.addEventListener('change', (e) => saveMaxSpreadSetting(e.target.value));
            }
            const maxSpreadNum = document.getElementById('input-max-spread-num');
            if (maxSpreadNum) {
                maxSpreadNum.addEventListener('input', (e) => updateMaxSpreadValue(e.target.value));
                maxSpreadNum.addEventListener('change', (e) => saveMaxSpreadSetting(e.target.value));
            }

            const apiUrlInput = document.getElementById('input-api-url');
            if (apiUrlInput) {
                apiUrlInput.addEventListener('change', (e) => saveApiUrlSetting(e.target.value));
            }

            // Action buttons
            const trainBtn = document.getElementById('btn-trigger-training');
            if (trainBtn) trainBtn.addEventListener('click', triggerTraining);

            const resetBtn = document.getElementById('btn-reset-settings');
            if (resetBtn) resetBtn.addEventListener('click', resetSettings);

            const panicBtn = document.getElementById('btn-panic-close');
            if (panicBtn) panicBtn.addEventListener('click', panicCloseAll);

            // Chart tool buttons (Support, Resistance, Clear, Measure, Auto Scroll, Fullscreen)
            const btnSupport = document.getElementById('btn-tool-support');
            if (btnSupport) btnSupport.addEventListener('click', () => toggleDrawingMode('support'));

            const btnResistance = document.getElementById('btn-tool-resistance');
            if (btnResistance) btnResistance.addEventListener('click', () => toggleDrawingMode('resistance'));

            const btnClear = document.getElementById('btn-tool-clear');
            if (btnClear) btnClear.addEventListener('click', clearDrawings);

            const btnMeasure = document.getElementById('btn-tool-measure');
            if (btnMeasure) btnMeasure.addEventListener('click', () => toggleDrawingMode('measure'));

            const btnAutoScroll = document.getElementById('btn-tool-autoscroll');
            if (btnAutoScroll) btnAutoScroll.addEventListener('click', toggleAutoScroll);

            const btnFullscreen = document.getElementById('btn-chart-fullscreen');
            if (btnFullscreen) btnFullscreen.addEventListener('click', toggleFullScreen);
        }

        // Bulletproof initialization: execute immediately if document is already loaded
        if (document.readyState === 'loading') {
            window.addEventListener('DOMContentLoaded', initDashboard);
        } else {
            initDashboard();
        }

        let chartRequestSequence = 0;
        let chartAbortController = null;

        async function fetchChartData() {
            const selectEl = document.getElementById('symbol-select');
            const requestedSymbol = selectEl?.value || 'XAUUSDm';
            const requestedTimeframe = activeTimeframe || 'M5';
            const requestSequence = ++chartRequestSequence;

            if (chartAbortController) {
                try { chartAbortController.abort(); } catch (e) {}
            }
            chartAbortController = new AbortController();

            try {
                const url = `${apiBase}/api/chart?symbol=${encodeURIComponent(requestedSymbol)}&timeframe=${encodeURIComponent(requestedTimeframe)}&_=${Date.now()}`;
                const response = await fetch(url, {
                    signal: chartAbortController.signal,
                    cache: 'no-store'
                });

                if (!response.ok) {
                    throw new Error(`Chart HTTP ${response.status}`);
                }

                const data = await response.json();

                // Ignore an old response that arrived after the user selected another timeframe.
                if (requestSequence !== chartRequestSequence || requestedTimeframe !== activeTimeframe) {
                    return;
                }

                const chartSnapshot = data.chart_snapshot || {};
                const marketState = data.market_state || {};

                const candles = Array.isArray(data.candles) ? data.candles :
                               (Array.isArray(chartSnapshot.candles) ? chartSnapshot.candles : []);

                const symbol = data.symbol || marketState.symbol || chartSnapshot.symbol || requestedSymbol;
                const timeframe = data.timeframe || marketState.timeframe || chartSnapshot.timeframe || requestedTimeframe;

                if (candles && candles.length > 0) {
                    const activeLevels = data.levels || chartSnapshot.levels || {};
                    canvasChart.setData(
                        candles,
                        activeLevels,
                        data.trades || chartSnapshot.trades || [],
                        data.fvgs || chartSnapshot.fvgs || [],
                        data.sweeps || chartSnapshot.sweeps || [],
                        data.mss_events || data.mss || chartSnapshot.mss_events || []
                    );
                    updateKeyLevelsBreakdown(candles, activeLevels, symbol);

                    const titleEl = document.getElementById('chart-symbol-title');
                    if (titleEl) {
                        titleEl.textContent = `📊 ${symbol} ${timeframe} Candlestick Chart`;
                    }
                } else {
                    console.warn(`No candles returned for ${symbol} ${timeframe}`);
                }

            } catch (error) {
                if (error.name === 'AbortError') {
                    return;
                }
                console.error('Failed to load chart:', error);
            } finally {
                if (requestSequence === chartRequestSequence) {
                    chartAbortController = null;
                }
            }
        }

        window.setTimeframe = function setTimeframe(tf) {
            const allowedTimeframes = new Set(['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']);
            tf = String(tf).toUpperCase();

            if (!allowedTimeframes.has(tf)) {
                console.error('Invalid timeframe:', tf);
                return;
            }

            activeTimeframe = tf;

            try {
                localStorage.setItem('pulse_viper_active_timeframe', tf);
            } catch (error) {
                console.warn('Unable to save timeframe:', error);
            }

            document.querySelectorAll('.tf-btn').forEach(button => {
                button.classList.remove('active');
            });

            const activeButton = document.getElementById(`btn-tf-${tf.toLowerCase()}`);
            if (activeButton) {
                activeButton.classList.add('active');
            }

            const countdown = document.getElementById('candle-countdown');
            if (countdown) {
                countdown.textContent = `${tf}: loading...`;
            }

            if (canvasChart) {
                canvasChart.autoScroll = true;
            }

            fetchChartData();
        };

        window.changeObsOverlayMode = function changeObsOverlayMode(mode) {
            const body = document.body;
            if (!body) return;
            if (mode === 'chroma-green') {
                body.style.backgroundColor = '#00ff00';
                body.style.backgroundImage = 'none';
            } else if (mode === 'chroma-magenta') {
                body.style.backgroundColor = '#ff00ff';
                body.style.backgroundImage = 'none';
            } else if (mode === 'transparent') {
                body.style.backgroundColor = 'transparent';
                body.style.backgroundImage = 'none';
            } else {
                body.style.backgroundColor = '#070a13';
                body.style.backgroundImage = '';
            }
        };

        let microScalpActive = false;
        window.toggleMicroScalpMode = function toggleMicroScalpMode() {
            microScalpActive = !microScalpActive;
            const btn = document.getElementById('btn-tool-micro-scalp');
            if (btn) {
                if (microScalpActive) {
                    btn.style.background = '#ffcc00';
                    btn.style.color = '#070a13';
                    btn.innerText = '⚡ Micro Scalp Mode: ON (0.01 lot, 12p SL, 24p TP)';
                } else {
                    btn.style.background = 'rgba(255, 204, 0, 0.15)';
                    btn.style.color = '#ffcc00';
                    btn.innerText = '⚡ Micro Scalp Mode';
                }
            }
        };

        window.executeCopilotTrade = async function executeCopilotTrade() {
            const btn = document.getElementById('btn-execute-copilot');
            if (btn) btn.innerText = microScalpActive ? "⚡ DISPATCHING MICRO SCALPS (0.01 LOT, 12P SL, 24P TP)..." : "⚡ DISPATCHING TO MT5...";
            try {
                const response = await fetch(`${apiBase}/api/execute_trade`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        symbol: requestedSymbol || 'XAUUSDm',
                        micro_scalp: microScalpActive
                    })
                });
                const res = await response.json();
                if (res.status === 'success') {
                    alert(`✅ Trade Executed on MT5 [${res.mode}]: ${res.action} @ ${res.entry} | Ticket: ${res.ticket}`);
                } else {
                    alert(`⚠️ Co-Pilot Notice: ${res.error || 'Setup not ready or market closed'}`);
                }
            } catch (err) {
                alert(`❌ Co-Pilot Execution Error: ${err.message}`);
            } finally {
                if (btn) btn.innerText = "🚀 EXECUTE CO-PILOT TRADE (1-CLICK MT5)";
            }
        };

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

        async function fetchLogs() {
            try {
                const response = await fetch(`${apiBase}/api/logs?_=${Date.now()}`);
                if (!response.ok) return;
                const data = await response.json();
                const logContainer = document.getElementById('live-logs');
                if (logContainer && data.logs && data.logs.length > 0) {
                    logContainer.innerHTML = data.logs.join('\\n');
                    // Auto-scroll to bottom of logs
                    logContainer.scrollTop = logContainer.scrollHeight;
                } else if (logContainer) {
                    logContainer.innerText = "No engine events logged yet.";
                }
            } catch (e) {
                console.error("Failed to load engine logs", e);
            }
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

        function toggleAutoScroll() {
            if (!canvasChart) return;
            canvasChart.autoScroll = !canvasChart.autoScroll;
            const btn = document.getElementById('btn-tool-autoscroll');
            if (btn) {
                btn.classList.toggle('active', canvasChart.autoScroll);
            }
            if (canvasChart.autoScroll) {
                canvasChart.offsetX = 0;
                canvasChart.draw();
            }
        }

        window.jumpToLatestTicks = function jumpToLatestTicks() {
            if (!canvasChart) return;
            canvasChart.offsetX = 0;
            canvasChart.offsetY = 0;
            canvasChart.autoScroll = true;
            const btnAuto = document.getElementById('btn-tool-autoscroll');
            const btnJump = document.getElementById('btn-jump-latest');
            if (btnAuto) btnAuto.classList.add('active');
            if (btnJump) btnJump.style.display = 'none';
            canvasChart.draw();
        };

        window.toggleChartOverlay = function toggleChartOverlay(type, isChecked) {
            if (!canvasChart) return;
            if (type === 'pos') canvasChart.showOverlayPos = isChecked;
            if (type === 'trend') canvasChart.showOverlayTrend = isChecked;
            if (type === 'ob') canvasChart.showOverlayOB = isChecked;
            canvasChart.draw();
        };

        function toggleFullScreen() {
            const chartCard = document.getElementById('chart-card');
            const fsBtn = document.getElementById('btn-chart-fullscreen');
            if (!chartCard) return;

            if (!document.fullscreenElement) {
                chartCard.requestFullscreen().catch(err => {
                    console.error('Error attempting to enable fullscreen:', err);
                });
                if (fsBtn) fsBtn.innerText = '🗗';
            } else {
                document.exitFullscreen().catch(err => {
                    console.error('Error attempting to exit fullscreen:', err);
                });
                if (fsBtn) fsBtn.innerText = '⛶';
            }
        }

        // Listen to fullscreen change to update button icon and overlays
        document.addEventListener('fullscreenchange', () => {
            const fsBtn = document.getElementById('btn-chart-fullscreen');
            if (fsBtn) {
                fsBtn.innerText = document.fullscreenElement ? '🗗' : '⛶';
            }
            
            document.body.classList.toggle('is-fullscreen', document.fullscreenElement != null);
            
            const overlay = document.getElementById('fullscreen-right-overlay');
            const sentCard = document.getElementById('sentiment-card');
            const volCard = document.getElementById('volume-card');
            
            if (document.fullscreenElement) {
                if (overlay && sentCard && volCard) {
                    overlay.style.display = 'flex';
                    overlay.appendChild(sentCard);
                    overlay.appendChild(volCard);
                    
                    // Add background styling to cards for floating effect
                    sentCard.style.background = 'rgba(7, 10, 19, 0.9)';
                    sentCard.style.border = '1px solid var(--glass-border)';
                    volCard.style.background = 'rgba(7, 10, 19, 0.9)';
                    volCard.style.border = '1px solid var(--glass-border)';
                }
            } else {
                if (overlay && sentCard && volCard) {
                    overlay.style.display = 'none';
                    document.getElementById('sentiment-card-wrapper').appendChild(sentCard);
                    document.getElementById('volume-card-wrapper').appendChild(volCard);
                    
                    // Reset styling
                    sentCard.style.background = '';
                    sentCard.style.border = '';
                    volCard.style.background = '';
                    volCard.style.border = '';
                }
            }
        });

        function updateKeyLevelsBreakdown(candles, levels, activeSymbol) {
            if (!levels) return;
            const symBadge = document.getElementById('levels-symbol-badge');
            if (symBadge) symBadge.innerText = activeSymbol || 'XAUUSDm';

            const lastCandle = (candles && candles.length > 0) ? candles[candles.length - 1] : null;
            const currentPrice = lastCandle ? lastCandle.close : 0.0;
            const priceEl = document.getElementById('lvl-current-price');
            if (priceEl) priceEl.innerText = currentPrice > 0 ? currentPrice.toFixed(currentPrice > 500 ? 2 : 5) : '--';

            function formatLevel(val) {
                if (val === null || val === undefined || isNaN(val) || val === 0) return '--';
                return val.toFixed(val > 500 ? 2 : 5);
            }

            function formatDist(levelVal) {
                if (levelVal === null || levelVal === undefined || isNaN(levelVal) || levelVal === 0 || !currentPrice) return '--';
                const diff = Math.abs(currentPrice - levelVal);
                const pts = currentPrice > 500 ? diff.toFixed(1) + ' pts' : (diff * 10000).toFixed(1) + ' pips';
                return (currentPrice >= levelVal ? '↓ ' : '↑ ') + pts;
            }

            // Support
            const elSup = document.getElementById('val-support'); if (elSup) elSup.innerText = formatLevel(levels.support);
            const elSupDist = document.getElementById('dist-support'); if (elSupDist) elSupDist.innerText = formatDist(levels.support);

            // Resistance
            const elRes = document.getElementById('val-resistance'); if (elRes) elRes.innerText = formatLevel(levels.resistance);
            const elResDist = document.getElementById('dist-resistance'); if (elResDist) elResDist.innerText = formatDist(levels.resistance);

            // POC
            const elPoc = document.getElementById('val-poc'); if (elPoc) elPoc.innerText = formatLevel(levels.poc);
            const elPocDist = document.getElementById('dist-poc'); if (elPocDist) elPocDist.innerText = formatDist(levels.poc);

            // OB Zone
            const elObRange = document.getElementById('val-ob-range');
            const elObType = document.getElementById('badge-ob-type');
            if (elObRange) {
                if (levels.ob_top && levels.ob_bottom) {
                    elObRange.innerText = `${formatLevel(levels.ob_bottom)} - ${formatLevel(levels.ob_top)}`;
                } else {
                    elObRange.innerText = '--';
                }
            }
            if (elObType) {
                const dir = (levels.ob_direction || 'none').toUpperCase();
                elObType.innerText = dir;
                elObType.style.color = dir === 'BULLISH' ? 'var(--color-green)' : (dir === 'BEARISH' ? 'var(--color-red)' : 'var(--text-muted)');
            }

            // VAH & VAL
            const elVah = document.getElementById('val-vah'); if (elVah) elVah.innerText = formatLevel(levels.vah);
            const elVahDist = document.getElementById('dist-vah'); if (elVahDist) elVahDist.innerText = formatDist(levels.vah);

            const elVal = document.getElementById('val-val'); if (elVal) elVal.innerText = formatLevel(levels.val);
            const elValDist = document.getElementById('dist-val'); if (elValDist) elValDist.innerText = formatDist(levels.val);

            // PDH / PDL
            const elPdhPdl = document.getElementById('val-pdh-pdl');
            if (elPdhPdl) {
                elPdhPdl.innerText = `${formatLevel(levels.pdh)} / ${formatLevel(levels.pdl)}`;
            }

            // PWH / PWL
            const elPwhPwl = document.getElementById('val-pwh-pwl');
            if (elPwhPwl) {
                elPwhPwl.innerText = `${formatLevel(levels.pwh)} / ${formatLevel(levels.pwl)}`;
            }
        }

        function toggleConfigDrawer(forceOpen) {
            const drawer = document.getElementById('config-drawer');
            const overlay = document.getElementById('config-overlay');
            if (!drawer || !overlay) return;
            const isCurrentlyOpen = drawer.classList.contains('open');
            const shouldOpen = (typeof forceOpen === 'boolean') ? forceOpen : !isCurrentlyOpen;
            if (shouldOpen) {
                drawer.classList.add('open');
                overlay.style.display = 'block';
            } else {
                drawer.classList.remove('open');
                overlay.style.display = 'none';
            }
        }

        async function changeSymbol(symbol) {
            lastSymbolChangeTime = Date.now();
            lastChangedTimes['active_symbol'] = Date.now();
            try {
                localStorage.setItem('pulse_viper_active_symbol', symbol);
            } catch (e) {}

            const selectEl = document.getElementById('symbol-select');
            if (selectEl) selectEl.value = symbol;

            await sendSettingUpdate({ "active_symbol": symbol });
            await new Promise(resolve => setTimeout(resolve, 150));

            await Promise.all([
                fetchStatus(),
                fetchChartData()
            ]);
        }

        async function addCustomSymbol() {
            const input = document.getElementById('custom-symbol-input');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) return;
            
            try {
                const btn = document.getElementById('btn-add-custom-symbol');
                const origText = btn ? btn.innerText : '+';
                if (btn) {
                    btn.innerText = '⌛';
                    btn.disabled = true;
                }
                const response = await fetch(`${apiBase}/api/add_symbol`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol })
                });
                
                const resData = await response.json();
                if (response.ok && resData.status === 'success') {
                    input.value = '';
                    await fetchStatus();
                    lastSymbolChangeTime = Date.now();
                    lastChangedTimes['active_symbol'] = Date.now();
                    try {
                        localStorage.setItem('pulse_viper_active_symbol', resData.symbol);
                    } catch (e) {}
                    const selectEl = document.getElementById('symbol-select');
                    if (selectEl) selectEl.value = resData.symbol;
                    fetchChartData();
                } else {
                    alert(resData.error || 'Failed to add symbol');
                }
            } catch (err) {
                console.error("Error adding symbol", err);
                alert("Error adding symbol: " + err.message);
            } finally {
                const btn = document.getElementById('btn-add-custom-symbol');
                if (btn) {
                    btn.innerText = '+';
                    btn.disabled = false;
                }
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

                // ── CRITICAL: Update symbol selector FIRST (before any other DOM ops that might crash) ──
                if (data.symbols && data.symbols.length > 0) {
                    const selectEl = document.getElementById('symbol-select');
                    const userIsChangingSymbol = (Date.now() - lastSymbolChangeTime < 15000);
                    let savedLocalSymbol = '';
                    try { savedLocalSymbol = localStorage.getItem('pulse_viper_active_symbol') || ''; } catch (e) {}
                    
                    let currentValue = userIsChangingSymbol ? selectEl.value : (settings.active_symbol || savedLocalSymbol || selectEl.value);

                    // Rebuild options if list changed or if active symbol is missing from dropdown options
                    let symbolList = Array.from(new Set([...data.symbols, currentValue].filter(Boolean)));
                    let currentOptions = Array.from(selectEl.options).map(o => o.value);
                    let needsRebuild = symbolList.length !== currentOptions.length || symbolList.some((s, idx) => currentOptions[idx] !== s);

                    if (needsRebuild) {
                        selectEl.innerHTML = '';
                        symbolList.forEach(sym => {
                            const opt = document.createElement('option');
                            opt.value = sym;
                            opt.text = sym;
                            opt.style.background = 'var(--bg-dark)';
                            opt.style.color = 'var(--text-primary)';
                            selectEl.appendChild(opt);
                        });
                        selectEl.value = currentValue;
                    } else if (!userIsChangingSymbol && selectEl.value !== currentValue) {
                        selectEl.value = currentValue;
                    }
                } else if (settings.active_symbol && Date.now() - lastSymbolChangeTime > 15000) {
                    const selectEl = document.getElementById('symbol-select');
                    if (selectEl && selectEl.value !== settings.active_symbol) {
                        selectEl.value = settings.active_symbol;
                    }
                }

                // ── Remaining dashboard updates (wrapped so symbol update above always completes) ──
                try {
                const brokerEl = document.getElementById('broker-name');
                if (brokerEl) brokerEl.innerText = `${data.account.broker.toUpperCase()} (${(data.account.mode || '').toUpperCase()})`;
                const latencyEl = document.getElementById('latency-lbl');
                if (latencyEl) latencyEl.innerText = `LATENCY: ${data.latency_ms} ms`;

                if (data.spread && data.spread.current !== null) {
                    const spreadLbl = document.getElementById('spread-lbl');
                    if (spreadLbl) spreadLbl.innerText = `SPREAD: ${data.spread.current} PTS (MAX: ${data.spread.max_limit})`;
                    const badge = document.getElementById('spread-badge');
                    if (badge) {
                        if (data.spread.exceeded) {
                            badge.style.borderColor = 'var(--color-red)';
                            badge.style.color = 'var(--color-red)';
                        } else {
                            badge.style.borderColor = 'var(--glass-border)';
                            badge.style.color = 'var(--text-primary)';
                        }
                    }
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
                const el_lbl_h1_bias = document.getElementById('lbl-h1-bias'); if (el_lbl_h1_bias) el_lbl_h1_bias.innerText = data.sentiment.h1_bias_label || 'Neutral';
                const el_lbl_m15_sweep = document.getElementById('lbl-m15-sweep'); if (el_lbl_m15_sweep) el_lbl_m15_sweep.innerText = data.sentiment.m15_sweep_label || 'Neutral';
                const el_lbl_m5_mss = document.getElementById('lbl-m5-mss'); if (el_lbl_m5_mss) el_lbl_m5_mss.innerText = data.sentiment.m5_mss_label || 'Neutral';

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
                const el_pred_type = document.getElementById('pred-type'); if (el_pred_type) el_pred_type.innerText = pred.setup_type || 'N/A';
                const el_pred_entry = document.getElementById('pred-entry'); if (el_pred_entry) el_pred_entry.innerText = pred.entry ? pred.entry.toFixed(5) : '--';
                const el_pred_sl = document.getElementById('pred-sl'); if (el_pred_sl) el_pred_sl.innerText = pred.sl ? pred.sl.toFixed(5) : '--';
                const el_pred_tp = document.getElementById('pred-tp'); if (el_pred_tp) el_pred_tp.innerText = pred.tp ? pred.tp.toFixed(5) : '--';
                const el_pred_lots = document.getElementById('pred-lots'); if (el_pred_lots) el_pred_lots.innerText = pred.lots ? pred.lots.toFixed(2) : '0.01';
                const el_pred_confidence = document.getElementById('pred-confidence'); if (el_pred_confidence) el_pred_confidence.innerText = pred.confidence ? `${pred.confidence}%` : '—';

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

                // Update VSA Patterns in sidebar
                const vsaPatterns = pred.vsa_patterns || [];
                const vsaEl = document.getElementById('pred-vsa');
                if (vsaEl) {
                    if (vsaPatterns.length > 0) {
                        vsaEl.innerHTML = vsaPatterns.map(p => {
                            const isBullish = ['SPRING', 'STOPPING_VOLUME', 'NO_SUPPLY', 'SELLING_CLIMAX'].includes(p);
                            const color = isBullish ? '#a855f7' : '#ec4899';
                            return `<span style="background: rgba(${isBullish?'168,85,247':'236,72,153'}, 0.15); border: 1px solid rgba(${isBullish?'168,85,247':'236,72,153'}, 0.4); border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 700; color: ${color}; text-shadow: 0 0 6px ${color}; margin-right: 4px; display: inline-block; margin-bottom: 2px;">${p}</span>`;
                        }).join('');
                    } else {
                        vsaEl.innerHTML = '<span style="color:var(--text-muted); font-size: 11px;">NONE</span>';
                    }
                }

                const headerSessionsEl = document.getElementById('header-sessions');
                if (headerSessionsEl) {
                    headerSessionsEl.innerHTML = sessions.length > 0
                        ? sessions.map(s => `<span style="background: rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.18); border: 1px solid rgba(${s==='Sydney'?'168,85,247':s==='Asian'?'245,158,11':s==='London'?'59,130,246':'16,185,129'}, 0.5); border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 700; color: ${sessionColors[s]||'var(--color-blue)'}; text-shadow: 0 0 6px currentColor; display: inline-block;">${s}</span>`).join('')
                        : '<span style="color:var(--text-muted); font-size: 11px; font-weight: 600;">NO ACTIVE SESSIONS</span>';
                }

                // ── 6-TF Cascade Alignment Panel ─────────────────────────────
                const tfAlign = pred.tf_alignment || data.tf_alignment || {};
                const biasLabel = (b, custom) => {
                    if (custom) {
                        const c = String(custom).toUpperCase();
                        if (c.includes('BULLISH')) return 'BULL';
                        if (c.includes('BEARISH')) return 'BEAR';
                        if (c.includes('NEUTRAL')) return 'NEUT';
                        if (c.includes('SELLING_CLIMAX')) return 'SC';
                        if (c.includes('BUYING_CLIMAX')) return 'BC';
                        if (c.includes('STOPPING')) return 'STP';
                        if (c.includes('NO_SUPPLY')) return 'NS';
                        if (c.includes('NO_DEMAND')) return 'ND';
                        if (c.includes('UPTHRUST')) return 'UT';
                        if (c.includes('SPRING')) return 'SPR';
                        if (c.includes('SWEEP')) return 'SWP';
                        if (c.includes('MSS')) return 'MSS';
                        if (c.includes('TBS')) return 'TBS';
                        return c.length > 5 ? c.substring(0, 5) : c;
                    }
                    if (b > 0) return 'BULL';
                    if (b < 0) return 'BEAR';
                    return 'NEUT';
                };
                const biasColor = (b, lbl) => {
                    if (lbl) {
                        if (lbl.includes('SPRING') || lbl.includes('NO_SUPPLY') || lbl.includes('STOPPING') || lbl.includes('SELLING_CLIMAX')) {
                            return '#a855f7'; // Purple for bullish VSA
                        }
                        if (lbl.includes('UPTHRUST') || lbl.includes('NO_DEMAND') || lbl.includes('BUYING_CLIMAX')) {
                            return '#ec4899'; // Pink/Magenta for bearish VSA
                        }
                        if (lbl.includes('SWEEP') || lbl.includes('MSS') || lbl.includes('TBS')) {
                            return '#ffd32a'; // Yellow for SMC execution
                        }
                    }
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
                const el_skip_spread = document.getElementById('skip-spread'); if (el_skip_spread) el_skip_spread.innerText = skipped.high_spread || 0;
                const el_skip_news = document.getElementById('skip-news'); if (el_skip_news) el_skip_news.innerText = (skipped.news_filter || 0) + (skipped.regime_filter || 0);
                const el_skip_brain = document.getElementById('skip-brain'); if (el_skip_brain) el_skip_brain.innerText = skipped.brain_filter || 0;



                // Positions Table
                const posBody = document.getElementById('positions-body');
                if (posBody) {
                    posBody.textContent = '';
                    if (data.positions && data.positions.length > 0) {
                        data.positions.forEach(p => {
                            const tr = document.createElement('tr');
                            
                            const tdId = document.createElement('td');
                            tdId.textContent = p.ticket || p.id || 'N/A';
                            tr.appendChild(tdId);
                            
                            const tdSymbol = document.createElement('td');
                            tdSymbol.textContent = p.symbol;
                            tr.appendChild(tdSymbol);
                            
                            const tdAction = document.createElement('td');
                            tdAction.textContent = p.action;
                            tdAction.style.color = p.action === 'BUY' ? 'var(--color-green)' : 'var(--color-red)';
                            tdAction.style.fontWeight = '700';
                            tr.appendChild(tdAction);
                            
                            const tdVol = document.createElement('td');
                            tdVol.textContent = p.volume ? p.volume.toFixed(2) : '0.00';
                            tr.appendChild(tdVol);
                            
                            const tdEntry = document.createElement('td');
                            tdEntry.textContent = p.entry_price ? p.entry_price.toFixed(5) : '0.00000';
                            tr.appendChild(tdEntry);
                            
                            const tdSl = document.createElement('td');
                            tdSl.textContent = p.sl ? p.sl.toFixed(5) : '0.00000';
                            tr.appendChild(tdSl);
                            
                            const tdTp = document.createElement('td');
                            tdTp.textContent = p.tp ? p.tp.toFixed(5) : '0.00000';
                            tr.appendChild(tdTp);
                            
                            const tdPnl = document.createElement('td');
                            const pnlVal = p.pnl || 0.0;
                            tdPnl.textContent = `$${pnlVal.toFixed(2)}`;
                            tdPnl.style.color = pnlVal >= 0 ? 'var(--color-green)' : 'var(--color-red)';
                            tdPnl.style.fontWeight = '700';
                            tr.appendChild(tdPnl);
                            
                            posBody.appendChild(tr);
                        });
                    } else {
                        const tr = document.createElement('tr');
                        const td = document.createElement('td');
                        td.colSpan = 8;
                        td.style.textAlign = 'center';
                        td.style.color = 'var(--text-muted)';
                        td.textContent = 'No open positions.';
                        tr.appendChild(td);
                        posBody.appendChild(tr);
                    }
                }

                // Update Global Strategy Routing Assistant
                const sug = data.strategy_suggestion || {};
                const rNameEl = document.getElementById('route-best-name'); if (rNameEl) rNameEl.innerText = sug.strategy || 'N/A';
                const rReasonEl = document.getElementById('route-best-reason'); if (rReasonEl) rReasonEl.innerText = sug.reason || 'No active suggestions.';
                const rWrEl = document.getElementById('route-best-wr'); if (rWrEl) rWrEl.innerText = sug.win_rate !== undefined ? `${sug.win_rate.toFixed(1)}%` : '--';
                const rPfEl = document.getElementById('route-best-pf'); if (rPfEl) rPfEl.innerText = sug.profit_factor !== undefined ? sug.profit_factor.toFixed(2) : '--';
                const rPnlEl = document.getElementById('route-best-pnl'); if (rPnlEl) rPnlEl.innerText = sug.net_pnl_R !== undefined ? `${sug.net_pnl_R > 0 ? '+' : ''}${sug.net_pnl_R.toFixed(1)}R` : '--';
                
                const rBadge = document.getElementById('route-score-badge');
                if (rBadge) {
                    const adj = sug.routing_adjustment || 0.0;
                    rBadge.innerText = `${adj >= 0 ? '+' : ''}${adj.toFixed(1)} pts`;
                    if (adj > 0) {
                        rBadge.style.backgroundColor = 'rgba(46, 204, 113, 0.15)';
                        rBadge.style.color = 'var(--color-green)';
                        rBadge.style.borderColor = 'rgba(46, 204, 113, 0.3)';
                    } else if (adj < 0) {
                        rBadge.style.backgroundColor = 'rgba(255, 71, 87, 0.15)';
                        rBadge.style.color = 'var(--color-red)';
                        rBadge.style.borderColor = 'rgba(255, 71, 87, 0.3)';
                    } else {
                        rBadge.style.backgroundColor = 'var(--glass-bg)';
                        rBadge.style.color = 'var(--text-muted)';
                        rBadge.style.borderColor = 'var(--glass-border)';
                    }
                }
                
                const rModeEl = document.getElementById('route-ctx-mode'); if (rModeEl) rModeEl.innerText = (sug.mode || settings.trading_mode || '--').toUpperCase();
                const rSessEl = document.getElementById('route-ctx-session'); if (rSessEl) rSessEl.innerText = sug.session || (sessions.length > 0 ? sessions[0] : '--').toUpperCase();
                const rRegEl = document.getElementById('route-ctx-regime'); if (rRegEl) rRegEl.innerText = data.market_regime || '--';

                const rankBody = document.getElementById('route-rankings-body');
                if (rankBody) {
                    if (data.strategy_rankings && data.strategy_rankings.length > 0) {
                        rankBody.innerHTML = data.strategy_rankings.slice(0, 5).map((r, idx) => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); ${idx === 0 ? 'background: rgba(0, 210, 211, 0.04); font-weight: 700;' : ''}">
                                <td style="padding: 6px 8px; color: ${idx === 0 ? 'var(--color-blue)' : 'var(--text-primary)'};">${idx + 1}. ${r.strategy}</td>
                                <td style="padding: 6px 8px;">${r.total_trades}</td>
                                <td style="padding: 6px 8px; color: var(--color-green);">${r.win_rate.toFixed(1)}%</td>
                                <td style="padding: 6px 8px; color: var(--color-gold);">${r.profit_factor.toFixed(2)}</td>
                            </tr>
                        `).join('');
                    } else {
                        rankBody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 12px; color: var(--text-muted);">No rankings for current state.</td></tr>`;
                    }
                }

                // History Table
                cachedHistory = data.history || [];
                renderHistoryTable();

                // Volume stats
                const vol = data.volume || {};
                const el_val_rvol = document.getElementById('val-rvol'); if (el_val_rvol) el_val_rvol.innerText = (vol.rvol || 1.0).toFixed(2);
                
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
                const el_lbl_pressure_buy = document.getElementById('lbl-pressure-buy'); if (el_lbl_pressure_buy) el_lbl_pressure_buy.innerText = `${buyPct}%`;
                const el_lbl_pressure_sell = document.getElementById('lbl-pressure-sell'); if (el_lbl_pressure_sell) el_lbl_pressure_sell.innerText = `${sellPct}%`;
                document.getElementById('bar-pressure-buy').style.width = `${buyPct}%`;

                // Volume Profile Poc Histogram
                const container = document.getElementById('vp-chart-container');
                const ctrlBadge = document.getElementById('vp-market-control-badge');
                if (vol.profile) {
                    const profile = vol.profile;
                    const buyPctVal = profile.overall_buy_pct !== undefined ? profile.overall_buy_pct : buyPct;
                    const isBuyControl = (profile.market_control === 'BUYERS' || buyPctVal >= 50.0);
                    
                    if (ctrlBadge) {
                        ctrlBadge.innerText = isBuyControl ? `BUYERS IN CONTROL (${buyPctVal.toFixed(0)}%) 🟢` : `SELLERS IN CONTROL (${(100 - buyPctVal).toFixed(0)}%) 🔴`;
                        ctrlBadge.style.backgroundColor = isBuyControl ? 'rgba(0, 240, 118, 0.15)' : 'rgba(255, 51, 102, 0.15)';
                        ctrlBadge.style.color = isBuyControl ? 'var(--color-green)' : 'var(--color-red)';
                        ctrlBadge.style.borderColor = isBuyControl ? 'rgba(0, 240, 118, 0.3)' : 'rgba(255, 51, 102, 0.3)';
                    }

                    if (container && profile.bin_volumes && profile.bin_volumes.length > 0) {
                        const volumes = profile.bin_volumes;
                        const buyVols = profile.buy_volumes || [];
                        const sellVols = profile.sell_volumes || [];
                        const edges = profile.bin_edges;
                        const max_vol = Math.max(...volumes, 1.0);
                        const poc = profile.poc_price;
                        
                        let html = "";
                        for (let i = volumes.length - 1; i >= 0; i--) {
                            const binPriceLow = edges[i];
                            const binPriceHigh = edges[i+1];
                            const binMid = (binPriceLow + binPriceHigh) / 2.0;
                            const isPoc = Math.abs(binMid - poc) < (binPriceHigh - binPriceLow)/2.0;
                            
                            const bVol = buyVols[i] !== undefined ? buyVols[i] : volumes[i] * (buyPct / 100.0);
                            const sVol = sellVols[i] !== undefined ? sellVols[i] : volumes[i] * (sellPct / 100.0);
                            const buyWidth = (bVol / max_vol) * 100.0;
                            const sellWidth = (sVol / max_vol) * 100.0;
                            
                            html += `
                                <div class="vp-bar-row ${isPoc ? 'poc' : ''}" style="display: flex; align-items: center; gap: 6px; font-size: 9px;">
                                    <div class="vp-price" style="width: 48px; color: ${isPoc ? 'var(--color-gold)' : 'var(--text-muted)'}; font-weight: ${isPoc ? '800' : '600'};">${binMid.toFixed(2)}</div>
                                    <div style="flex: 1; display: flex; height: 7px; background: rgba(255,255,255,0.04); border-radius: 3px; overflow: hidden;">
                                        <div style="width: ${buyWidth.toFixed(1)}%; background: #00f076;" title="Buy Volume: ${bVol.toFixed(1)}"></div>
                                        <div style="width: ${sellWidth.toFixed(1)}%; background: #ff3366;" title="Sell Volume: ${sVol.toFixed(1)}"></div>
                                    </div>
                                    ${isPoc ? `<span style="font-size: 8px; font-weight: 800; color: var(--color-gold); background: rgba(255, 204, 0, 0.15); border: 1px solid rgba(255, 204, 0, 0.3); padding: 0 4px; border-radius: 3px;">POC</span>` : ''}
                                </div>
                            `;
                        }
                        container.innerHTML = html;
                    }
                }

                // Settings - update individually unless modified recently by the user
                if (!isSettingModifiedRecently('auto_trade_enabled')) {
                    document.getElementById('toggle-autotrade').checked = settings.auto_trade_enabled !== false;
                }
                if (!isSettingModifiedRecently('paper_mode')) {
                    document.getElementById('toggle-paper').checked = settings.paper_mode || false;
                }
                if (!isSettingModifiedRecently('compounding_mode')) {
                    document.getElementById('toggle-compounding').checked = settings.compounding_mode || false;
                }
                if (!isSettingModifiedRecently('hedging_mode')) {
                    document.getElementById('toggle-hedging').checked = settings.hedging_mode || false;
                }
                if (!isSettingModifiedRecently('trailing_stop_enabled')) {
                    document.getElementById('toggle-trailing').checked = settings.trailing_stop_enabled || false;
                }
                if (!isSettingModifiedRecently('use_manual_lot')) {
                    document.getElementById('toggle-manual-lot').checked = settings.use_manual_lot || false;
                }
                if (!isSettingModifiedRecently('break_even_enabled')) {
                    document.getElementById('toggle-breakeven').checked = settings.break_even_enabled || false;
                }
                if (!isSettingModifiedRecently('news_filter_enabled')) {
                    document.getElementById('toggle-news-filter').checked = settings.news_filter_enabled || false;
                }
                if (!isSettingModifiedRecently('self_learning_filter')) {
                    document.getElementById('toggle-self-learning').checked = settings.self_learning_filter || false;
                }
                if (!isSettingModifiedRecently('strict_mode')) {
                    document.getElementById('toggle-strict-mode').checked = settings.strict_mode || false;
                }
                if (!isSettingModifiedRecently('dynamic_risk_enabled')) {
                    document.getElementById('toggle-dynamic-risk').checked = settings.dynamic_risk_enabled !== false;
                }
                if (!isSettingModifiedRecently('dynamic_regime_filter')) {
                    document.getElementById('toggle-regime-filter').checked = settings.dynamic_regime_filter !== false;
                }

                if (!isSettingModifiedRecently('risk_percent')) {
                    document.getElementById('input-risk').value = settings.risk_percent || 1.0;
                    const el_lbl_risk_val = document.getElementById('lbl-risk-val'); 
                    if (el_lbl_risk_val) el_lbl_risk_val.innerText = `${(settings.risk_percent || 1.0).toFixed(2)}%`;
                }
                if (!isSettingModifiedRecently('min_ai_confidence')) {
                    document.getElementById('input-min-ai-conf').value = settings.min_ai_confidence || 0.52;
                    const el_lbl_min_ai_conf_val = document.getElementById('lbl-min-ai-conf-val'); 
                    if (el_lbl_min_ai_conf_val) el_lbl_min_ai_conf_val.innerText = (settings.min_ai_confidence || 0.52).toFixed(2);
                }
                if (!isSettingModifiedRecently('max_daily_trades')) {
                    document.getElementById('input-max-daily').value = settings.max_daily_trades || 3;
                    const el_lbl_max_daily_val = document.getElementById('lbl-max-daily-val'); 
                    if (el_lbl_max_daily_val) el_lbl_max_daily_val.innerText = settings.max_daily_trades || 3;
                }
                if (!isSettingModifiedRecently('max_spread_points')) {
                    document.getElementById('input-max-spread').value = settings.max_spread_points || 300;
                    document.getElementById('input-max-spread-num').value = settings.max_spread_points || 300;
                    const el_lbl_max_spread_val = document.getElementById('lbl-max-spread-val'); 
                    if (el_lbl_max_spread_val) el_lbl_max_spread_val.innerText = `${settings.max_spread_points || 300} pts`;
                }
                if (!isSettingModifiedRecently('manual_lot_size')) {
                    const lotSize = settings.manual_lot_size || 0.01;
                    const inputManualLot = document.getElementById('input-manual-lot');
                    const inputManualLotNum = document.getElementById('input-manual-lot-num');
                    const el_lbl_manual_lot_val = document.getElementById('lbl-manual-lot-val');
                    if (inputManualLot) inputManualLot.value = lotSize;
                    if (inputManualLotNum) inputManualLotNum.value = lotSize;
                    if (el_lbl_manual_lot_val) el_lbl_manual_lot_val.innerText = `${parseFloat(lotSize).toFixed(2)} lots`;
                }

                if (!isSettingModifiedRecently('trading_mode')) {
                    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
                    const actMode = settings.trading_mode || 'intraday';
                    const activeModeBtn = document.getElementById(`btn-mode-${actMode}`);
                    if (activeModeBtn) activeModeBtn.classList.add('active');
                }

                // News Ribbon Update
                const newsTicker = document.getElementById('news-ticker-wrap');
                const fsNewsTicker = document.getElementById('fullscreen-news-ticker-wrap');
                if (data.sentiment.news_articles && data.sentiment.news_articles.length > 0) {
                    const newsHTML = data.sentiment.news_articles.map(art => `
                        <span class="ticker-item"><strong style="color: var(--color-gold);">•</strong> ${art.title}</span>
                    `).join('');
                    if (newsTicker) newsTicker.innerHTML = newsHTML;
                    if (fsNewsTicker) fsNewsTicker.innerHTML = newsHTML;
                }

                // Caution Ribbon Update
                const cautionTicker = document.getElementById('caution-ticker-wrap');
                const fsCautionTicker = document.getElementById('fullscreen-caution-ticker-wrap');
                if (cautionTicker || fsCautionTicker) {
                    let warnings = [];
                    warnings.push("🎓 FOR EDUCATIONAL & RESEARCH PURPOSES ONLY — TAKE ALL TRADING RISKS AT YOUR OWN DISCRETION");
                    warnings.push("TRADING INVOLVES SUBSTANTIAL RISK OF LOSS — PAST PERFORMANCE IS NOT INDICATIVE OF FUTURE RESULTS");
                    if (data.spread && data.spread.exceeded) {
                        warnings.push(`🚨 SPREAD LIMIT EXCEEDED ON ${data.spread.symbol}: ${data.spread.current} PTS (MAX ALLOWED: ${data.spread.max_limit})`);
                    }
                    if (data.margin_level !== 'N/A' && parseFloat(data.margin_level) < 200.0) {
                        warnings.push(`🚨 MARGIN LEVEL IS EXTREMELY LOW: ${data.margin_level} — SUSPENDING NEW TRADES`);
                    }
                    if (data.positions && data.positions.length > 0) {
                        warnings.push(`💼 MONITORING ${data.positions.length} ACTIVE TRADES — FLOATING PNL: $${data.account.profit.toFixed(2)}`);
                    }
                    warnings.push("PULSE VIPER IS AN EDUCATIONAL & QUANTITATIVE ANALYTICAL TOOL — DO NOT TRADE WITH MONEY YOU CANNOT AFFORD TO LOSE");
                    warnings.push("ALWAYS VERIFY SIGNALS WITH YOUR OWN INDEPENDENT ANALYSIS — NO STRATEGY GUARANTEES PROFIT");
                    
                    const warningsHTML = warnings.map(w => `
                        <span class="ticker-item">${w}</span>
                    `).join('');
                    if (cautionTicker) cautionTicker.innerHTML = warningsHTML;
                    if (fsCautionTicker) fsCautionTicker.innerHTML = warningsHTML;
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
                    const el_pred_patterns = document.getElementById('pred-patterns'); if (el_pred_patterns) el_pred_patterns.innerText = pred.detected_patterns.join(', ');
                } else {
                    const el_pred_patterns = document.getElementById('pred-patterns'); if (el_pred_patterns) el_pred_patterns.innerText = 'NONE';
                }
                const clusters = {
                    0: 'Consolidation (Cluster 0)',
                    1: 'Expansion (Cluster 1)',
                    2: 'Volatile Chop (Cluster 2)',
                    3: 'Trend Reversal (Cluster 3)'
                };
                
                // Update Market Regime (Pill)
                const regimeEl = document.getElementById('pred-regime');
                if (regimeEl && pred.market_regime) {
                    regimeEl.innerText = pred.market_regime;
                    regimeEl.className = `regime-pill regime-${pred.market_regime.toLowerCase()}`;
                } else if (regimeEl) {
                    regimeEl.innerText = clusters[pred.cluster_id] || 'RANGING';
                    regimeEl.className = '';
                }

                // Update News Lockout Banner
                const lockoutBanner = document.getElementById('news-lockout-banner');
                const lockoutDetails = document.getElementById('news-lockout-details');
                if (lockoutBanner && lockoutDetails) {
                    if (pred.news_locked) {
                        lockoutBanner.style.display = 'flex';
                        lockoutDetails.innerText = pred.news_lockout_reason || 'High impact economic news active. Gated lockout enforced.';
                    } else {
                        lockoutBanner.style.display = 'none';
                    }
                }

                // Update Resting Liquidity Pools
                const poolsContainer = document.getElementById('liquidity-pools-container');
                const poolCountEl = document.getElementById('pool-count');
                if (poolsContainer && poolCountEl) {
                    const pools = pred.resting_pools || [];
                    poolCountEl.innerText = `${pools.length} Active`;
                    if (pools.length > 0) {
                        poolsContainer.innerHTML = pools.map(p => {
                            const isBuyStop = p.type === 'BUY_STOP';
                            const badgeColor = isBuyStop ? 'var(--color-green)' : 'var(--color-red)';
                            const badgeText = isBuyStop ? 'BSL' : 'SSL';
                            return `
                                <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:6px 10px; border-radius:6px; font-size:11px;">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="font-size:8px; font-weight:800; padding:2px 4px; border-radius:3px; background:${badgeColor}15; color:${badgeColor}; border:1px solid ${badgeColor}30;">${badgeText}</span>
                                        <span style="font-weight:600; color:var(--text-primary);">${p.pool_id}</span>
                                    </div>
                                    <div style="display:flex; flex-direction:column; align-items:flex-end;">
                                        <span style="font-family:'Outfit',sans-serif; font-weight:700; color:var(--text-primary);">${p.price.toFixed(2)}</span>
                                        <span style="font-size:9px; color:var(--text-muted);">${p.touches} touches</span>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    } else {
                        poolsContainer.innerHTML = `<span style="color:var(--text-muted); font-size:11px; text-align:center; padding:5px;">No active liquidity pools mapped.</span>`;
                    }
                }

                // ── Phase 9 v2: Brain Score Gauge Update ─────────────────────────────
                const brainArc = document.getElementById('brain-arc');
                const brainScoreText = document.getElementById('brain-score-text');
                const brainLabelText = document.getElementById('brain-label-text');
                const brainDirectionBadge = document.getElementById('brain-direction-badge');
                const brainThresholdDisplay = document.getElementById('brain-threshold-display');
                const brainBreakdownBars = document.getElementById('brain-breakdown-bars');
                const brainBlockReason = document.getElementById('brain-block-reason');

                if (brainArc && pred.brain_score !== undefined) {
                    const score = parseFloat(pred.brain_score) || 0;
                    const threshold = parseFloat(pred.brain_threshold) || 55;
                    const label = pred.brain_label || 'BLOCKED';
                    const direction = pred.brain_direction;
                    const blockReason = pred.brain_block_reason || '';
                    const t1 = parseFloat(pred.brain_tier1) || 0;
                    const t2 = parseFloat(pred.brain_tier2) || 0;
                    const t3 = parseFloat(pred.brain_tier3) || 0;

                    // ── Arc gauge animation ──
                    const arcLength = 172.8;
                    const offset = arcLength - (score / 100) * arcLength;
                    brainArc.style.strokeDashoffset = offset.toFixed(1);

                    // ── Color zone ──
                    let scoreColor = '#ff3366';
                    if (score >= 75) scoreColor = '#00ff88';
                    else if (score >= 55) scoreColor = '#ffcc00';
                    else if (score >= 40) scoreColor = '#ff8800';

                    // ── Score text + label ──
                    if (brainScoreText) brainScoreText.textContent = Math.round(score);
                    if (brainLabelText) { brainLabelText.textContent = label; brainLabelText.style.color = scoreColor; }
                    if (brainThresholdDisplay) brainThresholdDisplay.textContent = Math.round(threshold);

                    // ── Block reason display ──
                    if (brainBlockReason) {
                        const reasonLabel = {
                            'NEWS_LOCKOUT': 'NEWS LOCK',
                            'CHAOTIC_REGIME': 'CHAOTIC',
                            'SCORE_BELOW_THRESHOLD': 'LOW SCORE',
                            'DIRECTIONAL_CONFLICT': 'CONFLICT',
                            'KILLZONE_INACTIVE': 'INACTIVE KZ',
                            'NEWS_SENTIMENT_VETO': 'NEWS VETO',
                            'NO_HTF_LEVEL': 'NO HTF LVL',
                            'BLOCK_REASON_ROLLOVER_LIQUIDITY_GAP': 'LIQ GAP',
                            'BLOCK_REASON_GOLD_DEAD_ZONE': 'DEAD ZONE',
                            'BLOCK_REASON_FX_LOW_VELOCITY': 'LOW VELOC',
                        };
                        const displayReason = reasonLabel[blockReason] || blockReason || '';
                        brainBlockReason.textContent = (displayReason === 'none' || displayReason === 'None') ? '' : displayReason;
                        brainBlockReason.style.color = (direction && (!blockReason || blockReason === 'none' || blockReason === 'None')) ? '#00ff88' : '#ff8800';
                    }

                    // ── Direction badge ──
                    if (brainDirectionBadge) {
                        if (direction === 'BUY') {
                            brainDirectionBadge.textContent = '\u25b2 BUY';
                            brainDirectionBadge.style.background = 'rgba(0,220,130,0.15)';
                            brainDirectionBadge.style.color = '#00dc82';
                            brainDirectionBadge.style.borderColor = 'rgba(0,220,130,0.4)';
                        } else if (direction === 'SELL') {
                            brainDirectionBadge.textContent = '\u25bc SELL';
                            brainDirectionBadge.style.background = 'rgba(255,51,102,0.15)';
                            brainDirectionBadge.style.color = '#ff3366';
                            brainDirectionBadge.style.borderColor = 'rgba(255,51,102,0.4)';
                        } else {
                            const badge = blockReason === 'DIRECTIONAL_CONFLICT' ? '\u2296 CONFLICT' : '\u2014 IDLE';
                            brainDirectionBadge.textContent = badge;
                            brainDirectionBadge.style.background = 'rgba(255,255,255,0.05)';
                            brainDirectionBadge.style.color = 'rgba(255,255,255,0.4)';
                            brainDirectionBadge.style.borderColor = 'rgba(255,255,255,0.1)';
                        }
                    }

                    // ── Tier score bars (T1/50, T2/35, T3/15) ──
                    const tier1Bar = document.getElementById('brain-tier1-bar');
                    const tier2Bar = document.getElementById('brain-tier2-bar');
                    const tier3Bar = document.getElementById('brain-tier3-bar');
                    const tier1Val = document.getElementById('brain-tier1-val');
                    const tier2Val = document.getElementById('brain-tier2-val');
                    const tier3Val = document.getElementById('brain-tier3-val');
                    if (tier1Bar) tier1Bar.style.width = ((t1 / 50) * 100).toFixed(1) + '%';
                    if (tier2Bar) tier2Bar.style.width = ((t2 / 35) * 100).toFixed(1) + '%';
                    if (tier3Bar) tier3Bar.style.width = ((t3 / 15) * 100).toFixed(1) + '%';
                    if (tier1Val) tier1Val.textContent = t1.toFixed(0) + '/50';
                    if (tier2Val) tier2Val.textContent = t2.toFixed(0) + '/35';
                    if (tier3Val) tier3Val.textContent = t3.toFixed(0) + '/15';

                    // ── Component micro-bars (v2 key names) ──
                    if (brainBreakdownBars) {
                        const reasonMap = pred.brain_reason_map || {};
                        // v2 reason_map uses t1_*, t2_*, t3_* prefixed keys
                        const compDefs = [
                            { key: 't1_d1',           label: 'D1 Bias',   max: 18  },
                            { key: 't1_h4',           label: 'H4 Bias',   max: 14  },
                            { key: 't1_h1',           label: 'H1 Bias',   max: 11  },
                            { key: 't2_structure',    label: 'Structure', max: 12  },
                            { key: 't2_fvg',          label: 'FVG',       max: 7   },
                            { key: 't2_vsa',          label: 'VSA',       max: 10  },
                            { key: 't2_volume',       label: 'Volume',    max: 4   },
                            { key: 't2_ai_confidence',label: 'AI Conf',   max: 8   },
                            { key: 't3_regime_quality', label: 'Regime',  max: 15  },
                            { key: 'strategy_confirm', label: 'Strategy', max: 2   },
                        ].filter(d => reasonMap[d.key] !== undefined && Math.abs(reasonMap[d.key]) > 0);

                        if (compDefs.length > 0) {
                            brainBreakdownBars.innerHTML = compDefs.map(d => {
                                const val = parseFloat(reasonMap[d.key]) || 0;
                                const absVal = Math.abs(val);
                                const pct = d.max > 0 ? Math.min(100, (absVal / d.max) * 100) : 0;
                                const isNeg = val < 0;
                                const barCol = isNeg ? '#ff3366' : (pct >= 70 ? '#00ff88' : pct >= 35 ? '#ffcc00' : '#5577ff');
                                return `<div style="display:flex;align-items:center;gap:5px;font-size:9px;">
                                    <span style="width:48px;color:rgba(255,255,255,0.42);flex-shrink:0;overflow:hidden;white-space:nowrap;">${d.label}</span>
                                    <div style="flex:1;height:4px;background:rgba(255,255,255,0.07);border-radius:2px;overflow:hidden;">
                                        <div style="width:${pct.toFixed(1)}%;height:100%;background:${barCol};border-radius:2px;transition:width 0.6s ease;"></div>
                                    </div>
                                    <span style="width:24px;text-align:right;color:rgba(255,255,255,0.5);font-weight:700;">${isNeg ? '-' : ''}${absVal.toFixed(0)}</span>
                                </div>`;
                            }).join('');
                        } else {
                            brainBreakdownBars.innerHTML = '';
                        }
                    }
                }

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
                const el_diag_leverage = document.getElementById('diag-leverage'); if (el_diag_leverage) el_diag_leverage.innerText = data.leverage || 'N/A';
                const el_diag_margin_level = document.getElementById('diag-margin-level'); if (el_diag_margin_level) el_diag_margin_level.innerText = data.margin_level || 'N/A';
                
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

                // Update Safety diagnostics elements (Phase 10)
                const safetyHaltEl = document.getElementById('diag-safety-halt');
                if (safetyHaltEl) {
                    if (pred.safety_halt) {
                        safetyHaltEl.innerText = 'HALTED 🛑';
                        safetyHaltEl.style.color = 'var(--color-red)';
                    } else {
                        safetyHaltEl.innerText = 'PASSED 🟢';
                        safetyHaltEl.style.color = 'var(--color-green)';
                    }
                }

                const sStats = pred.safety_stats || {};
                const dailyPnlEl = document.getElementById('diag-daily-pnl');
                if (dailyPnlEl && sStats.daily_pnl !== undefined) {
                    const dPnl = parseFloat(sStats.daily_pnl) || 0;
                    const dPct = bal > 0 ? (dPnl / bal) * 100.0 : 0;
                    dailyPnlEl.innerHTML = `<span style="color:${dPnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${dPnl.toFixed(2)} (${dPnl >= 0 ? '+' : ''}${dPct.toFixed(2)}%)</span>`;
                }

                const weeklyPnlEl = document.getElementById('diag-weekly-pnl');
                if (weeklyPnlEl && sStats.weekly_pnl !== undefined) {
                    const wPnl = parseFloat(sStats.weekly_pnl) || 0;
                    const wPct = bal > 0 ? (wPnl / bal) * 100.0 : 0;
                    weeklyPnlEl.innerHTML = `<span style="color:${wPnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${wPnl.toFixed(2)} (${wPnl >= 0 ? '+' : ''}${wPct.toFixed(2)}%)</span>`;
                }

                const consecLossesEl = document.getElementById('diag-consec-losses');
                if (consecLossesEl && sStats.consecutive_losses !== undefined) {
                    const consec = parseInt(sStats.consecutive_losses) || 0;
                    consecLossesEl.innerText = consec;
                    consecLossesEl.style.color = consec > 0 ? 'var(--color-red)' : 'var(--text-primary)';
                }

                // Update Forex Session Badge (Phase 10) and Session Remaining
                const forexSessionBadge = document.getElementById('forex-session-badge');
                const sessionRemainingEl = document.getElementById('session-remaining');
                if (data.session_context) {
                    const sContext = data.session_context;
                    const sName = sContext.session_name || 'OFF';
                    const sScore = parseFloat(sContext.session_score) || 0;
                    const remMin = parseInt(sContext.remaining_minutes) || 0;
                    // Format remaining time as HH:MM or MM mins
                    let remText;
                    if (remMin >= 60) {
                        const remH = Math.floor(remMin / 60);
                        const remM = remMin % 60;
                        remText = `${remH}h ${remM}m`;
                    } else {
                        remText = `${remMin}m`;
                    }
                    if (forexSessionBadge) {
                        forexSessionBadge.textContent = `${sName} (${sScore.toFixed(1)} PTS)`;
                        if (sName === 'OVERLAP' || sName.includes('OVERLAP')) {
                            forexSessionBadge.style.color = '#00ff88'; // green
                            forexSessionBadge.style.background = 'rgba(0, 255, 136, 0.15)';
                            forexSessionBadge.style.borderColor = 'rgba(0, 255, 136, 0.4)';
                        } else if (sName.includes('LONDON') || sName.includes('NEW_YORK')) {
                            forexSessionBadge.style.color = '#00a8ff'; // blue
                            forexSessionBadge.style.background = 'rgba(0, 168, 255, 0.15)';
                            forexSessionBadge.style.borderColor = 'rgba(0, 168, 255, 0.4)';
                        } else if (sName.includes('ASIAN')) {
                            forexSessionBadge.style.color = '#ffcc00'; // yellow
                            forexSessionBadge.style.background = 'rgba(255, 204, 0, 0.15)';
                            forexSessionBadge.style.borderColor = 'rgba(255, 204, 0, 0.4)';
                        } else {
                            forexSessionBadge.style.color = 'var(--text-muted)';
                            forexSessionBadge.style.background = 'rgba(255,255,255,0.05)';
                            forexSessionBadge.style.borderColor = 'rgba(255,255,255,0.1)';
                        }
                    }
                    if (sessionRemainingEl) {
                        sessionRemainingEl.textContent = remText;
                    }
                } else if (forexSessionBadge && pred.session_name) {
                    const sName = pred.session_name;
                    const sScore = parseFloat(pred.session_score) || 0;
                    forexSessionBadge.textContent = `${sName} (${sScore.toFixed(1)} PTS)`;
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
                // Update Fullscreen PnL Card if it exists
                const fsPnlCard = document.getElementById('fs-pnl-card');
                if (fsPnlCard) {
                    if (data.positions && data.positions.length > 0) {
                        fsPnlCard.style.display = 'block';
                        const actionBadge = document.getElementById('fs-pnl-action');
                        const valText = document.getElementById('fs-pnl-value');
                        
                        // Default to the action of the first position
                        const primaryAction = data.positions[0].action;
                        actionBadge.innerText = primaryAction;
                        actionBadge.style.color = primaryAction === 'BUY' ? 'var(--color-green)' : 'var(--color-red)';
                        actionBadge.style.background = primaryAction === 'BUY' ? 'rgba(0,240,118,0.1)' : 'rgba(255,51,102,0.1)';
                        
                        let totalPnl = 0;
                        data.positions.forEach(p => totalPnl += (p.pnl || 0));
                        valText.innerText = (totalPnl >= 0 ? '+' : '') + '$' + totalPnl.toFixed(2);
                        valText.style.color = totalPnl >= 0 ? 'var(--color-green)' : 'var(--color-red)';
                        fsPnlCard.style.border = '1px solid ' + (totalPnl >= 0 ? 'rgba(0,240,118,0.4)' : 'rgba(255,51,102,0.4)');
                    } else {
                        fsPnlCard.style.display = 'none';
                    }
                }

                } catch (innerErr) {
                    console.warn("Non-critical dashboard update error:", innerErr);
                }

            } catch (e) {
                console.error("Failed to poll status", e);
                // Visual feedback for connection failure
                const brokerEl = document.getElementById('broker-name');
                if (brokerEl) {
                    brokerEl.innerText = 'DISCONNECTED 🔴';
                    brokerEl.style.color = 'var(--color-red)';
                }
                const latencyEl = document.getElementById('latency-lbl');
                if (latencyEl) latencyEl.innerText = `LATENCY: --`;
                const spreadEl = document.getElementById('spread-lbl');
                if (spreadEl) spreadEl.innerText = `SPREAD: --`;
                
                const mt5El = document.getElementById('diag-mt5');
                if (mt5El) {
                    mt5El.innerText = 'DISCONNECTED 🔴';
                    mt5El.style.color = 'var(--color-red)';
                }
            }
        }

        function updateDial(id, valId, rawValue, isNews = false) {
            const dial = document.getElementById(id);
            const valEl = document.getElementById(valId);
            if (!dial || !valEl) return;

            let score = Number(rawValue);
            if (!Number.isFinite(score)) {
                score = 0;
            }

            const percent = ((score + 1.0) / 2.0) * 100;
            const isAvailable = Number.isFinite(Number(rawValue));

            if (isNews) {
                valEl.innerText = isAvailable ? score.toFixed(2) : '--';
            } else {
                valEl.innerText = isAvailable ? `${Math.round(score * 100)}%` : '--';
            }

            const filled = (percent / 100) * 94; // 94 units max for cx=35 r=30
            dial.style.strokeDasharray = `${filled} 188`;

            let color = 'var(--text-muted)';
            if (isAvailable) {
                if (score > 0.15) {
                    color = 'var(--color-green)';
                } else if (score < -0.15) {
                    color = 'var(--color-red)';
                }
            }
            dial.style.stroke = color;

            const dirId = valId.replace('val-', 'dir-');
            const dirEl = document.getElementById(dirId);
            if (dirEl) {
                if (!isAvailable) {
                    dirEl.innerText = '◆ Neutral';
                    dirEl.style.color = 'var(--text-muted)';
                } else if (score > 0.15) {
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
            else if (key === 'strict_mode') chk = document.getElementById('toggle-strict-mode').checked;
            else if (key === 'dynamic_risk_enabled') chk = document.getElementById('toggle-dynamic-risk').checked;
            else if (key === 'dynamic_regime_filter') chk = document.getElementById('toggle-regime-filter').checked;
            
            lastChangedTimes[key] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ [key]: chk });
        }

        async function setTradingMode(mode) {
            lastChangedTimes['trading_mode'] = Date.now();
            lastSettingsChangeTime = Date.now();
            // Optimistically update button active state
            document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
            const activeModeBtn = document.getElementById(`btn-mode-${mode}`);
            if (activeModeBtn) activeModeBtn.classList.add('active');
            
            sendSettingUpdate({ "trading_mode": mode });
        }

        function updateRiskValue(val) {
            lastChangedTimes['risk_percent'] = Date.now();
            const el_lbl_risk_val = document.getElementById('lbl-risk-val'); 
            if (el_lbl_risk_val) el_lbl_risk_val.innerText = `${parseFloat(val).toFixed(2)}%`;
        }

        async function saveRiskSetting(val) {
            lastChangedTimes['risk_percent'] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ "risk_percent": parseFloat(val) });
        }

        function updateMinAIConfValue(val) {
            lastChangedTimes['min_ai_confidence'] = Date.now();
            const el_lbl_min_ai_conf_val = document.getElementById('lbl-min-ai-conf-val'); 
            if (el_lbl_min_ai_conf_val) el_lbl_min_ai_conf_val.innerText = parseFloat(val).toFixed(2);
        }

        async function saveMinAIConfSetting(val) {
            lastChangedTimes['min_ai_confidence'] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ "min_ai_confidence": parseFloat(val) });
        }

        function updateMaxDailyValue(val) {
            lastChangedTimes['max_daily_trades'] = Date.now();
            const el_lbl_max_daily_val = document.getElementById('lbl-max-daily-val'); 
            if (el_lbl_max_daily_val) el_lbl_max_daily_val.innerText = val;
        }

        async function saveMaxDailySetting(val) {
            lastChangedTimes['max_daily_trades'] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ "max_daily_trades": parseInt(val) });
        }

        function updateMaxSpreadValue(val) {
            lastChangedTimes['max_spread_points'] = Date.now();
            const el_lbl_max_spread_val = document.getElementById('lbl-max-spread-val'); if (el_lbl_max_spread_val) el_lbl_max_spread_val.innerText = `${val} pts`;
            const rangeEl = document.getElementById('input-max-spread');
            const numEl = document.getElementById('input-max-spread-num');
            if (rangeEl) rangeEl.value = val;
            if (numEl) numEl.value = val;
        }

        async function saveMaxSpreadSetting(val) {
            lastChangedTimes['max_spread_points'] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ "max_spread_points": parseInt(val) });
        }

        function updateManualLotValue(val) {
            lastChangedTimes['manual_lot_size'] = Date.now();
            const el_lbl_manual_lot_val = document.getElementById('lbl-manual-lot-val'); 
            if (el_lbl_manual_lot_val) el_lbl_manual_lot_val.innerText = `${parseFloat(val).toFixed(2)} lots`;
            const rangeEl = document.getElementById('input-manual-lot');
            const numEl = document.getElementById('input-manual-lot-num');
            if (rangeEl) rangeEl.value = val;
            if (numEl) numEl.value = val;
        }

        async function saveManualLotSetting(val) {
            lastChangedTimes['manual_lot_size'] = Date.now();
            lastSettingsChangeTime = Date.now();
            sendSettingUpdate({ "manual_lot_size": parseFloat(val) });
        }

        async function sendSettingUpdate(payload) {
            // Update individual timestamps for keys in payload
            for (let key in payload) {
                lastChangedTimes[key] = Date.now();
            }
            lastSettingsChangeTime = Date.now();
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

        async function resetSettings() {
            if (confirm("⚠️ Are you sure you want to reset all settings to default values?")) {
                // Clear all local change times so we immediately accept new settings from server
                for (let k in lastChangedTimes) delete lastChangedTimes[k];
                lastSettingsChangeTime = 0;
                try {
                    const response = await fetch(`${apiBase}/api/reset_settings`, { method: 'POST' });
                    if (response.ok) {
                        alert("✅ All settings reset to default!");
                        fetchStatus(); // Refresh to load new settings
                    }
                } catch (e) {
                    console.error("Failed to reset settings", e);
                }
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

        function setHistoryFilter(filter) {
            historyFilter = filter;
            document.querySelectorAll('#btn-hist-daily, #btn-hist-weekly').forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.getElementById(`btn-hist-${filter}`);
            if (activeBtn) activeBtn.classList.add('active');
            renderHistoryTable();
        }

        function renderHistoryTable() {
            const histBody = document.getElementById('history-body');
            if (!histBody) return;

            let filtered = [];
            const now = new Date();
            
            // Format today's date in local client timezone (YYYY-MM-DD)
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const todayStr = `${year}-${month}-${day}`;

            if (historyFilter === 'daily') {
                filtered = cachedHistory.filter(h => {
                    if (!h.close_time) return false;
                    // Format matching
                    if (h.close_time.startsWith(todayStr)) return true;
                    // Parse matching for cross-timezone robustness
                    try {
                        const closeDate = new Date(h.close_time.replace(/-/g, '/'));
                        return closeDate.getDate() === now.getDate() &&
                               closeDate.getMonth() === now.getMonth() &&
                               closeDate.getFullYear() === now.getFullYear();
                    } catch (e) {
                        return false;
                    }
                });
            } else if (historyFilter === 'weekly') {
                const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                filtered = cachedHistory.filter(h => {
                    if (!h.close_time) return false;
                    try {
                        const closeDate = new Date(h.close_time.replace(/-/g, '/'));
                        return closeDate >= sevenDaysAgo;
                    } catch (e) {
                        return false;
                    }
                });
            } else {
                filtered = cachedHistory;
            }

            if (filtered.length > 0) {
                // Reverse it so most recent closed trade is at the top
                histBody.innerHTML = filtered.slice().reverse().map(h => `
                    <tr>
                        <td style="font-size:10px; font-family:monospace; color:var(--text-muted);">${h.close_time}</td>
                        <td>${h.symbol}</td>
                        <td style="color:${h.action === 'BUY' ? 'var(--color-green)' : 'var(--color-red)'};">${h.action}</td>
                        <td>${h.volume.toFixed(2)}</td>
                        <td>${h.entry_price.toFixed(5)}</td>
                        <td>${h.close_price.toFixed(5)}</td>
                        <td style="font-weight:700; color:var(--color-blue);">${h.strategy_name || 'UNKNOWN'}</td>
                        <td style="font-size:11px; color:var(--text-muted);">${h.entry_pattern || 'UNKNOWN'}</td>
                        <td>${h.close_reason}</td>
                        <td style="color:${h.pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}; font-weight:700;">$${h.pnl.toFixed(2)}</td>
                    </tr>
                `).join('');
            } else {
                histBody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No closed trades for this period.</td></tr>`;
            }
        }
    </script>
</body>
</html>
"""

BROADCAST_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>PULSE VIPER | BROADCAST MODE</title>
    <style>
        :root {
            --broadcast-sidebar: 320px;
            --broadcast-gap: 12px;
            --header-height: 48px;
            --timeline-height: 58px;
            --color-bg: #070a13;
            --color-panel: #0a0e18;
            --color-border: rgba(255, 255, 255, 0.10);
            --color-green: #00e676;
            --color-red: #ff4d6d;
            --color-gold: #f2a900;
            --color-blue: #00b8ff;
            --color-text: #f4f7fb;
            --color-text-muted: #8c96a8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', 'Inter', sans-serif;
            background: var(--color-bg);
            color: var(--color-text);
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            display: grid;
            grid-template-rows: var(--header-height) 1fr var(--timeline-height);
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 20px;
            background: var(--color-panel);
            border-bottom: 1px solid var(--color-border);
            font-size: 15px;
            font-weight: 700;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .header-logo {
            color: var(--color-gold);
            font-size: 18px;
            letter-spacing: 1px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 20px;
            color: var(--color-text-muted);
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(0, 230, 118, 0.1);
            color: var(--color-green);
            font-size: 13px;
        }

        .status-badge.disconnected {
            background: rgba(255, 77, 109, 0.1);
            color: var(--color-red);
        }

        main {
            min-height: 0;
            display: grid;
            grid-template-columns: minmax(0, 1fr) var(--broadcast-sidebar);
            gap: var(--broadcast-gap);
            padding: 10px 12px;
        }

        .chart-container {
            position: relative;
            border: 1px solid var(--color-border);
            border-radius: 10px;
            overflow: hidden;
            background: var(--color-panel);
            height: 100%;
            width: 100%;
        }

        canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: block;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 12px;
            min-height: 0;
            overflow-y: auto;
        }

        .sidebar-card {
            background: var(--color-panel);
            border: 1px solid var(--color-border);
            border-radius: 10px;
            padding: 15px;
        }

        .sidebar-card h3 {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--color-text-muted);
            margin-bottom: 12px;
            border-bottom: 1px solid var(--color-border);
            padding-bottom: 6px;
        }

        .market-metrics {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-size: 13px;
        }

        .metric-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .metric-item label {
            color: var(--color-text-muted);
        }

        .metric-item strong {
            font-size: 15px;
            color: var(--color-text);
        }

        /* Signal display */
        .broadcast-signal-card {
            display: flex;
            flex-direction: column;
            gap: 10px;
            border-radius: 10px;
            padding: 15px;
            background: rgba(140, 150, 168, 0.05);
            border: 1.5px solid var(--state-color, #8c96a8);
        }

        .signal-status {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--state-color, #8c96a8);
            font-weight: 700;
        }

        .signal-action {
            font-size: 36px;
            font-weight: 900;
            color: var(--state-color, #8c96a8);
            text-transform: uppercase;
        }

        .signal-meta {
            display: flex;
            gap: 12px;
            font-size: 14px;
            color: var(--color-text-muted);
        }

        .signal-prices {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
            margin-top: 5px;
        }

        .signal-prices label {
            font-size: 11px;
            color: var(--color-text-muted);
            display: block;
        }

        .signal-prices strong {
            font-size: 20px;
            color: var(--color-text);
        }

        .signal-quality {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            font-size: 13px;
            border-top: 1px dashed var(--color-border);
            padding-top: 8px;
        }

        .signal-quality strong {
            color: var(--color-text);
        }

        .signal-expiry {
            font-size: 13px;
            color: var(--color-text-muted);
            border-top: 1px dashed var(--color-border);
            padding-top: 8px;
            text-align: center;
        }

        /* Timeline */
        .timeline {
            display: flex;
            align-items: center;
            justify-content: space-around;
            background: var(--color-panel);
            border-top: 1px solid var(--color-border);
            padding: 0 30px;
            font-weight: 700;
        }

        .timeline-step {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--color-text-muted);
            font-size: 13px;
        }

        .timeline-step.active {
            color: var(--color-gold);
        }

        .timeline-step.completed {
            color: var(--color-green);
        }

        .risk-banner {
            text-align: center;
            font-size: 11px;
            color: var(--color-text-muted);
            letter-spacing: 2px;
            background: rgba(0, 0, 0, 0.2);
            padding: 2px 0;
            border-top: 1px solid var(--color-border);
        }

        /* State colors mapping */
        [data-state="scanning"] { --state-color: #8c96a8; }
        [data-state="candidate"] { --state-color: #f2a900; }
        [data-state="ready-buy"] { --state-color: #00e676; }
        [data-state="ready-sell"] { --state-color: #ff4d6d; }
        [data-state="blocked"] { --state-color: #ffb020; }
        [data-state="position-open"] { --state-color: #00b8ff; }
    </style>
</head>
<body>

    <header>
        <div class="header-left">
            <span class="header-logo">PULSE VIPER</span>
            <span id="header-symbol-tf">XAUUSD | M5 | INTRADAY</span>
        </div>
        <div class="header-right">
            <span id="session-label">NY SESSION</span>
            <span id="clock-utc">14:35 UTC</span>
            <div id="conn-badge" class="status-badge">CONNECTED</div>
        </div>
    </header>

    <main>
        <div class="chart-container" id="chart-container">
            <!-- Tri-layered high-performance canvases -->
            <canvas id="canvas-static"></canvas>
            <canvas id="canvas-structure"></canvas>
            <canvas id="canvas-live"></canvas>
        </div>

        <div class="sidebar">
            <div class="sidebar-card">
                <h3>Market State</h3>
                <div class="market-metrics">
                    <div class="metric-item">
                        <label>Regime</label>
                        <strong id="market-regime">Wait Regime</strong>
                    </div>
                    <div class="metric-item">
                        <label>Quality Gate</label>
                        <strong id="market-quality">97%</strong>
                    </div>
                    <div class="metric-item">
                        <label>Spread</label>
                        <strong id="market-spread">0.0 pips</strong>
                    </div>
                    <div class="metric-item">
                        <label>HTF Trend</label>
                        <strong id="market-trend">NEUTRAL</strong>
                    </div>
                </div>
            </div>

            <!-- Visual Signal Card Component -->
            <aside class="broadcast-signal-card" id="signal-card" data-state="scanning">
                <div class="signal-status" id="signal-status">SCANNING MARKET</div>
                <div class="signal-action" id="signal-action">SCANNING</div>
                <div class="signal-meta">
                    <span id="meta-symbol">-</span>
                    <span id="meta-tf">-</span>
                    <span id="meta-strategy">-</span>
                </div>
                <div class="signal-prices">
                    <div>
                        <label>ENTRY</label>
                        <strong id="price-entry">-</strong>
                    </div>
                    <div>
                        <label>STOP</label>
                        <strong id="price-stop">-</strong>
                    </div>
                    <div>
                        <label>TARGET</label>
                        <strong id="price-target">-</strong>
                    </div>
                </div>
                <div class="signal-quality">
                    <div>Win Prob: <strong id="quality-prob">-</strong></div>
                    <div>Expected R: <strong id="quality-ev">-</strong></div>
                    <div>Uncertainty: <strong id="quality-unc">-</strong></div>
                    <div style="display:none;">Planned RR: <strong id="quality-rr">-</strong></div>
                </div>
                <div class="signal-expiry" id="signal-expiry">
                    Scanning for setups...
                </div>
            </aside>
        </div>
    </main>

    <footer>
        <div class="timeline">
            <div class="timeline-step" id="step-scanning">1. SCANNING</div>
            <span>→</span>
            <div class="timeline-step" id="step-sweep">2. LIQUIDITY SWEEP</div>
            <span>→</span>
            <div class="timeline-step" id="step-mss">3. STRUCTURE SHIFT</div>
            <span>→</span>
            <div class="timeline-step" id="step-retest">4. ENTRY RETEST</div>
            <span>→</span>
            <div class="timeline-step" id="step-ready">5. SIGNAL READY</div>
        </div>
        <div class="risk-banner">
            EDUCATIONAL SYSTEM • AUTOMATED SIGNALS • TRADING INVOLVES RISK
        </div>
    </footer>

    <script>
        // High-performance double-buffered Canvas rendering
        const canvases = {
            static: document.getElementById('canvas-static'),
            structure: document.getElementById('canvas-structure'),
            live: document.getElementById('canvas-live')
        };
        const ctxs = {
            static: canvases.static.getContext('2d'),
            structure: canvases.structure.getContext('2d'),
            live: canvases.live.getContext('2d')
        };

        let snapshot = null;
        let lastCycleId = null;
        let candlesHash = null;

        // Auto zoom focus parameters
        let zoomCandles = 80;
        let zoomTarget = 80;

        function resizeCanvases() {
            const container = document.getElementById('chart-container');
            const w = container.clientWidth;
            const h = container.clientHeight;
            
            for (let id in canvases) {
                canvases[id].width = w;
                canvases[id].height = h;
            }
            drawStatic();
            drawStructure();
            drawLive();
        }

        window.addEventListener('resize', resizeCanvases);
        setTimeout(resizeCanvases, 100);

        // SSE Connection and fallbacks
        function connectSSE() {
            const stream = new EventSource("/api/broadcast/stream");
            
            stream.addEventListener("tick", event => {
                const tick = JSON.parse(event.data);
                updateTick(tick);
            });

            stream.addEventListener("chart_snapshot", event => {
                const snap = JSON.parse(event.data);
                applySnapshot(snap);
            });

            stream.onerror = () => {
                stream.close();
                document.getElementById('conn-badge').innerText = "DISCONNECTED";
                document.getElementById('conn-badge').classList.add('disconnected');
                // Poll fallback
                setTimeout(connectSSE, 5000);
            };
            
            document.getElementById('conn-badge').innerText = "CONNECTED";
            document.getElementById('conn-badge').classList.remove('disconnected');
        }

        connectSSE();

        // Clock UTC update
        setInterval(() => {
            const now = new Date();
            const utcStr = now.toISOString().replace('T', ' ').substring(11, 19) + ' UTC';
            document.getElementById('clock-utc').innerText = utcStr;
        }, 1000);

        function updateTick(tick) {
            // Live overlay ticker draw
            drawLive(tick);
        }

        function applySnapshot(snap) {
            snapshot = snap;
            
            // 1. Update Market state panels
            const state = snap.market_state || {};
            document.getElementById('header-symbol-tf').innerText = `${state.symbol || 'XAUUSD'} | ${state.timeframe || 'M5'} | ${state.mode || 'INTRADAY'}`;
            document.getElementById('market-regime').innerText = (state.regime || 'WAITING').replace(/_/g, ' ');
            document.getElementById('market-quality').innerText = `${Math.round((state.data_quality || 0.97)*100)}%`;
            document.getElementById('market-trend').innerText = snap.trend_state?.direction || 'NEUTRAL';
            document.getElementById('session-label').innerText = `${state.session || 'NY'} SESSION`;

            // Update spreads
            const spreadPts = snap.spread?.current_spread || 0.0;
            document.getElementById('market-spread').innerText = `${(spreadPts * 0.1).toFixed(1)} pips`;

            // 2. Update Signal Cards
            updateSignalCard(snap);

            // 3. Auto focus zoom transition
            const sig = snap.signal || {};
            if (sig.state === "SIGNAL_READY" || sig.state === "POSITION_OPEN") {
                zoomTarget = 40; // Focus zoom
            } else {
                zoomTarget = 85; // Normal scanning
            }

            // Draw canvases
            drawStatic();
            drawStructure();
            drawLive();
        }

        function updateSignalCard(snap) {
            const card = document.getElementById('signal-card');
            const status = document.getElementById('signal-status');
            const action = document.getElementById('signal-action');
            const sig = snap.signal || {};

            // Default privacy mode checks: hiding broker info, master tokens
            const symbol = snap.market_state?.symbol || "-";
            const tf = snap.market_state?.timeframe || "-";
            
            document.getElementById('meta-symbol').innerText = symbol;
            document.getElementById('meta-tf').innerText = tf;
            document.getElementById('meta-strategy').innerText = sig.strategy || "NONE";

            // State mappings
            if (sig.state === "SIGNAL_READY") {
                card.setAttribute('data-state', sig.action === "BUY" ? "ready-buy" : "ready-sell");
                status.innerText = "SIGNAL READY";
                action.innerText = sig.action;
                
                document.getElementById('price-entry').innerText = sig.entry_price || "-";
                document.getElementById('price-stop').innerText = sig.stop_price || "-";
                document.getElementById('price-target').innerText = sig.target_price || "-";
                
                document.getElementById('quality-prob').innerText = `${Math.round((sig.probability || 0.5) * 100)}%`;
                document.getElementById('quality-ev').innerText = `+${(sig.conservative_ev_r || 0.0).toFixed(2)}R`;
                document.getElementById('quality-unc').innerText = sig.uncertainty > 0.15 ? "HIGH" : "LOW";
                document.getElementById('quality-rr').innerText = `${(sig.planned_rr || 2.0).toFixed(2)}R`;
                document.getElementById('signal-expiry').innerText = "Valid for setup candles";
            } else if (sig.state === "POSITION_OPEN") {
                card.setAttribute('data-state', "position-open");
                status.innerText = "LIVE POSITION";
                action.innerText = sig.action;
                
                document.getElementById('price-entry').innerText = sig.entry_price || "-";
                document.getElementById('price-stop').innerText = sig.stop_price || "-";
                document.getElementById('price-target').innerText = sig.target_price || "-";
                document.getElementById('signal-expiry').innerText = "Managing position...";
            } else {
                card.setAttribute('data-state', "scanning");
                status.innerText = "SCANNING MARKET";
                action.innerText = "SCANNING";
                
                document.getElementById('price-entry').innerText = "-";
                document.getElementById('price-stop').innerText = "-";
                document.getElementById('price-target').innerText = "-";
                document.getElementById('signal-expiry').innerText = "Scanning for setups...";
            }

            // Update Timeline steps
            const stepScanning = document.getElementById('step-scanning');
            const stepSweep = document.getElementById('step-sweep');
            const stepMss = document.getElementById('step-mss');
            const stepRetest = document.getElementById('step-retest');
            const stepReady = document.getElementById('step-ready');

            // Reset
            [stepScanning, stepSweep, stepMss, stepRetest, stepReady].forEach(s => {
                s.className = "timeline-step";
            });

            if (sig.state === "SIGNAL_READY") {
                stepReady.classList.add('completed');
                stepRetest.classList.add('completed');
                stepMss.classList.add('completed');
                stepSweep.classList.add('completed');
            } else if (sig.state === "WAITING_FOR_ENTRY") {
                stepRetest.classList.add('active');
                stepMss.classList.add('completed');
                stepSweep.classList.add('completed');
            } else {
                stepScanning.classList.add('active');
            }
        }

        // Zoom animation loop
        function animateZoom() {
            if (Math.abs(zoomCandles - zoomTarget) > 0.5) {
                zoomCandles += (zoomTarget - zoomCandles) * 0.1; // Smooth 10% interpolation
                drawStatic();
                drawStructure();
                drawLive();
            }
            requestAnimationFrame(animateZoom);
        }
        requestAnimationFrame(animateZoom);

        // Drawing Layers on Canvas
        function drawStatic() {
            const ctx = ctxs.static;
            const w = canvases.static.width;
            const h = canvases.static.height;
            ctx.clearRect(0, 0, w, h);

            if (!snapshot || !snapshot.candles || snapshot.candles.length === 0) return;

            // Draw clean grids
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
            ctx.lineWidth = 1;
            const gridCount = 8;
            for (let i = 1; i < gridCount; i++) {
                // Vertical grid lines
                const x = (w / gridCount) * i;
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, h);
                ctx.stroke();

                // Horizontal grid lines
                const y = (h / gridCount) * i;
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(w, y);
                ctx.stroke();
            }

            // Draw candles
            const candles = snapshot.candles;
            const count = Math.min(candles.length, Math.round(zoomCandles));
            const viewCandles = candles.slice(-count);

            const highs = viewCandles.map(c => c.high);
            const lows = viewCandles.map(c => c.low);
            const maxPrice = Math.max(...highs);
            const minPrice = Math.min(...lows);
            const priceRange = maxPrice - minPrice;

            const padTop = h * 0.15;
            const padBottom = h * 0.15;
            const plotH = h - padTop - padBottom;

            function getY(p) {
                return padTop + plotH * (1 - (p - minPrice) / (priceRange || 1));
            }

            const candleW = (w * 0.8) / count;
            const gap = (w * 0.2) / count;

            for (let i = 0; i < count; i++) {
                const c = viewCandles[i];
                const x = i * (candleW + gap) + gap;

                const oY = getY(c.open);
                const cY = getY(c.close);
                const hY = getY(c.high);
                const lY = getY(c.low);

                const isBull = c.close >= c.open;
                ctx.strokeStyle = isBull ? varColor('green') : varColor('red');
                ctx.fillStyle = isBull ? varColor('green') : varColor('red');
                ctx.lineWidth = Math.max(1, candleW * 0.1);

                // Wick
                ctx.beginPath();
                ctx.moveTo(x + candleW / 2, hY);
                ctx.lineTo(x + candleW / 2, lY);
                ctx.stroke();

                // Body
                const top = Math.min(oY, cY);
                const bot = Math.max(oY, cY);
                const bodyH = Math.max(2, bot - top);
                ctx.fillRect(x, top, candleW, bodyH);
            }
        }

        function drawStructure() {
            const ctx = ctxs.structure;
            const w = canvases.structure.width;
            const h = canvases.structure.height;
            ctx.clearRect(0, 0, w, h);

            if (!snapshot || !snapshot.candles) return;

            // Enforce visual priorities Layer 2: Confirmed swings (External, Intermediate, Micro)
            const candles = snapshot.candles;
            const count = Math.min(candles.length, Math.round(zoomCandles));
            const viewCandles = candles.slice(-count);

            const highs = viewCandles.map(c => c.high);
            const lows = viewCandles.map(c => c.low);
            const maxPrice = Math.max(...highs);
            const minPrice = Math.min(...lows);
            const priceRange = maxPrice - minPrice;
            const plotH = h - h * 0.3;

            function getY(p) {
                return h * 0.15 + plotH * (1 - (p - minPrice) / (priceRange || 1));
            }

            const candleW = (w * 0.8) / count;
            const gap = (w * 0.2) / count;

            // Draw swings
            const swings = snapshot.swings || [];
            ctx.font = "bold 11px Arial";
            ctx.textAlign = "center";

            swings.forEach(s => {
                // Find candle index
                const idx = viewCandles.findIndex(c => c.time === s.pivot_time);
                if (idx !== -1) {
                    const x = idx * (candleW + gap) + gap + candleW / 2;
                    const y = getY(s.price);

                    ctx.fillStyle = s.direction === "HIGH" ? varColor('red') : varColor('green');
                    // Draw label
                    const label = s.scale === "MAJOR" ? "EH" : (s.scale === "MICRO" ? "μH" : "IH");
                    const labelLow = s.scale === "MAJOR" ? "EL" : (s.scale === "MICRO" ? "μL" : "IL");
                    
                    ctx.fillText(s.direction === "HIGH" ? label : labelLow, x, s.direction === "HIGH" ? y - 10 : y + 20);
                }
            });

            // Draw institutional FVG & OB Zones (Layer 4)
            const obs = snapshot.order_blocks || [];
            obs.forEach(ob => {
                const topY = getY(ob.top);
                const botY = getY(ob.bottom);
                
                ctx.fillStyle = ob.direction === "BULLISH" ? "rgba(0, 230, 118, 0.15)" : "rgba(255, 77, 109, 0.15)";
                ctx.fillRect(0, topY, w, botY - topY);
                
                ctx.strokeStyle = ob.direction === "BULLISH" ? "rgba(0, 230, 118, 0.3)" : "rgba(255, 77, 109, 0.3)";
                ctx.strokeRect(0, topY, w, botY - topY);
            });
        }

        function drawLive(tick = null) {
            const ctx = ctxs.live;
            const w = canvases.live.width;
            const h = canvases.live.height;
            ctx.clearRect(0, 0, w, h);

            if (!snapshot || !snapshot.candles) return;

            const candles = snapshot.candles;
            const count = Math.min(candles.length, Math.round(zoomCandles));
            const viewCandles = candles.slice(-count);
            const lastCandle = viewCandles[viewCandles.length - 1];

            const highs = viewCandles.map(c => c.high);
            const lows = viewCandles.map(c => c.low);
            const maxPrice = Math.max(...highs);
            const minPrice = Math.min(...lows);
            const priceRange = maxPrice - minPrice;
            const plotH = h - h * 0.3;

            function getY(p) {
                return h * 0.15 + plotH * (1 - (p - minPrice) / (priceRange || 1));
            }

            // Draw solid executable trade lines (Layer 6)
            const sig = snapshot.signal || {};
            if (sig.state === "SIGNAL_READY" || sig.state === "POSITION_OPEN") {
                const entryY = getY(sig.entry_price || lastCandle.close);
                const slY = getY(sig.stop_price || lastCandle.close);
                const tpY = getY(sig.target_price || lastCandle.close);

                ctx.lineWidth = 2.5;

                // Entry
                ctx.strokeStyle = varColor('blue');
                ctx.beginPath(); ctx.moveTo(0, entryY); ctx.lineTo(w, entryY); ctx.stroke();
                ctx.fillStyle = varColor('blue');
                ctx.fillText("ENTRY", 50, entryY - 6);

                // Stop Loss
                ctx.strokeStyle = varColor('red');
                ctx.beginPath(); ctx.moveTo(0, slY); ctx.lineTo(w, slY); ctx.stroke();
                ctx.fillStyle = varColor('red');
                ctx.fillText("STOP LOSS", 50, slY - 6);

                // Take Profit
                ctx.strokeStyle = varColor('green');
                ctx.beginPath(); ctx.moveTo(0, tpY); ctx.lineTo(w, tpY); ctx.stroke();
                ctx.fillStyle = varColor('green');
                ctx.fillText("TAKE PROFIT", 50, tpY - 6);
            }
        }

        function varColor(name) {
            if (name === 'green') return '#00e676';
            if (name === 'red') return '#ff4d6d';
            if (name === 'gold') return '#f2a900';
            if (name === 'blue') return '#00b8ff';
            return '#f4f7fb';
        }
    </script>
</body>
</html>
"""

