# dashboard/html_template.py
"""
Pulse Viper web dashboard.

Design goals:
- Read-only polling never evaluates trading logic.
- No external-data innerHTML.
- No manual trade execution controls.
- Quiet chart defaults.
- Real bid/ask from SSE.
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pulse Viper</title>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link
    href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap"
    rel="stylesheet"
>

<style>
:root {
    --bg: #070b12;
    --panel: #0d1420;
    --panel2: #111a29;
    --line: #223047;

    --text: #e8eef8;
    --muted: #8ea0b9;

    --green: #22c55e;
    --red: #ef4444;
    --amber: #f59e0b;
    --blue: #38bdf8;
    --violet: #a78bfa;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: Outfit, system-ui, sans-serif;
}

button,
input,
select {
    font: inherit;
}

button {
    cursor: pointer;
}

.shell {
    max-width: 1600px;
    margin: auto;
    padding: 18px;
}

.topbar {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 14px;
}

.brand {
    font-weight: 700;
    font-size: 21px;
}

.muted {
    color: var(--muted);
}

.pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;

    border: 1px solid var(--line);
    background: var(--panel);

    padding: 7px 10px;
    border-radius: 999px;

    font-size: 12px;
}

.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
}

.grid {
    display: grid;
    gap: 12px;
}

.kpis {
    grid-template-columns:
        repeat(
            6,
            minmax(
                130px,
                1fr
            )
        );

    margin-bottom: 12px;
}

.card {
    background:
        linear-gradient(
            180deg,
            var(--panel2),
            var(--panel)
        );

    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 13px;
}

.kpi-label {
    font-size: 11px;
    color: var(--muted);

    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.kpi-value {
    font-size: 20px;
    font-weight: 700;
    margin-top: 5px;
}

.main {
    grid-template-columns:
        minmax(
            0,
            2fr
        )
        minmax(
            320px,
            0.85fr
        );
}

.stack {
    display: grid;
    gap: 12px;
}

.card-title {
    font-size: 12px;
    color: var(--muted);

    text-transform: uppercase;
    letter-spacing: 0.06em;

    margin-bottom: 10px;
}

.chart-head {
    display: flex;
    justify-content: space-between;
    align-items: center;

    gap: 8px;
    flex-wrap: wrap;

    margin-bottom: 8px;
}

.controls {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.btn,
.field {
    border: 1px solid var(--line);
    background: #0a111c;
    color: var(--text);

    border-radius: 8px;
    padding: 7px 9px;
}

.btn.active {
    border-color: var(--blue);
    color: var(--blue);
}

.btn.danger {
    border-color: #5b2020;
    color: #fca5a5;
}

.btn.good {
    border-color: #14532d;
    color: #86efac;
}

canvas {
    width: 100%;
    height: 560px;

    display: block;

    background: #060a11;
    border-radius: 9px;
}

.quote {
    font-size: 12px;
    color: var(--muted);
}

.quote b {
    color: var(--text);
}

.row {
    display: flex;
    justify-content: space-between;

    gap: 14px;

    padding: 6px 0;

    border-bottom:
        1px solid
        rgba(
            255,
            255,
            255,
            0.04
        );
}

.row:last-child {
    border-bottom: 0;
}

.row span:first-child {
    color: var(--muted);
}

.table-wrap {
    overflow: auto;
    max-height: 300px;
}

table {
    width: 100%;
    border-collapse: collapse;

    font-size: 12px;
}

th,
td {
    text-align: left;
    padding: 8px;

    border-bottom:
        1px solid
        var(--line);

    white-space: nowrap;
}

th {
    color: var(--muted);
    font-weight: 500;
}

.section {
    margin-top: 12px;
}

.two {
    grid-template-columns:
        1fr
        1fr;
}

label {
    display: grid;
    gap: 5px;

    font-size: 11px;
    color: var(--muted);
}

input,
select {
    width: 100%;
}

.status-good {
    color: var(--green);
}

.status-bad {
    color: var(--red);
}

.status-warn {
    color: var(--amber);
}

.news-list {
    display: grid;
    gap: 7px;

    max-height: 240px;
    overflow: auto;
}

.news-item {
    border:
        1px solid
        var(--line);

    border-radius: 8px;
    padding: 8px;
}

.news-meta {
    font-size: 11px;
    color: var(--muted);

    margin-top: 3px;
}

.footer {
    color: var(--muted);
    font-size: 11px;

    margin:
        14px
        0
        4px;
}

@media (
    max-width: 1100px
) {
    .kpis {
        grid-template-columns:
            repeat(
                3,
                1fr
            );
    }

    .main {
        grid-template-columns:
            1fr;
    }
}

@media (
    max-width: 650px
) {
    .shell {
        padding: 10px;
    }

    .kpis {
        grid-template-columns:
            repeat(
                2,
                1fr
            );
    }

    .two {
        grid-template-columns:
            1fr;
    }

    canvas {
        height: 430px;
    }
}
</style>
</head>

<body>

<div class="shell">

    <div class="topbar">

        <div>
            <div class="brand">
                PULSE VIPER
            </div>

            <div
                class="muted"
                id="cycle-line"
            >
                Waiting for immutable
                engine snapshot…
            </div>
        </div>

        <div class="controls">

            <span class="pill">
                <span
                    class="dot"
                    id="conn-dot"
                ></span>

                <span id="conn-text">
                    INITIALIZING
                </span>
            </span>

            <span
                class="pill"
                id="mode-pill"
            >
                PAPER
            </span>

            <span
                class="pill"
                id="regime-pill"
            >
                REGIME —
            </span>

        </div>
    </div>


    <div class="grid kpis">

        <div class="card">
            <div class="kpi-label">
                Balance
            </div>

            <div
                class="kpi-value"
                id="balance"
            >
                —
            </div>
        </div>


        <div class="card">
            <div class="kpi-label">
                Equity
            </div>

            <div
                class="kpi-value"
                id="equity"
            >
                —
            </div>
        </div>


        <div class="card">
            <div class="kpi-label">
                Floating P&amp;L
            </div>

            <div
                class="kpi-value"
                id="pnl"
            >
                —
            </div>
        </div>


        <div class="card">
            <div class="kpi-label">
                Bid
            </div>

            <div
                class="kpi-value"
                id="bid"
            >
                —
            </div>
        </div>


        <div class="card">
            <div class="kpi-label">
                Ask
            </div>

            <div
                class="kpi-value"
                id="ask"
            >
                —
            </div>
        </div>


        <div class="card">
            <div class="kpi-label">
                Spread
            </div>

            <div
                class="kpi-value"
                id="spread"
            >
                —
            </div>
        </div>

    </div>


    <div class="grid main">

        <div class="stack">

            <section class="card">

                <div class="chart-head">

                    <div>
                        <div
                            class="card-title"
                            style="margin:0"
                        >
                            Market chart
                        </div>

                        <div class="quote">

                            <b id="chart-symbol">
                                —
                            </b>

                            <span id="chart-tf">
                                M5
                            </span>

                        </div>
                    </div>


                    <div class="controls">

                        <select
                            class="field"
                            id="symbol-select"
                            aria-label="Symbol"
                        ></select>


                        <select
                            class="field"
                            id="tf-select"
                            aria-label="Timeframe"
                        >
                            <option>
                                M1
                            </option>

                            <option selected>
                                M5
                            </option>

                            <option>
                                M15
                            </option>

                            <option>
                                M30
                            </option>

                            <option>
                                H1
                            </option>

                            <option>
                                H4
                            </option>

                            <option>
                                D1
                            </option>
                        </select>


                        <button
                            class="btn active"
                            id="toggle-pos"
                            type="button"
                        >
                            Positions
                        </button>


                        <button
                            class="btn active"
                            id="toggle-structure"
                            type="button"
                        >
                            Structure
                        </button>


                        <button
                            class="btn"
                            id="toggle-ob"
                            type="button"
                        >
                            OB
                        </button>


                        <button
                            class="btn"
                            id="toggle-trend"
                            type="button"
                        >
                            Trend
                        </button>


                        <button
                            class="btn"
                            id="toggle-ema"
                            type="button"
                        >
                            EMA
                        </button>


                        <button
                            class="btn"
                            id="toggle-vp"
                            type="button"
                        >
                            Volume Profile
                        </button>

                    </div>
                </div>


                <canvas
                    id="chart"
                    aria-label="Candlestick chart"
                ></canvas>

            </section>


            <div class="grid two">

                <section class="card">

                    <div class="card-title">
                        Open positions
                    </div>


                    <div class="table-wrap">

                        <table>

                            <thead>
                                <tr>
                                    <th>
                                        Symbol
                                    </th>

                                    <th>
                                        Side
                                    </th>

                                    <th>
                                        Lots
                                    </th>

                                    <th>
                                        Entry
                                    </th>

                                    <th>
                                        SL
                                    </th>

                                    <th>
                                        TP
                                    </th>

                                    <th>
                                        P&amp;L
                                    </th>
                                </tr>
                            </thead>


                            <tbody
                                id="positions-body"
                            ></tbody>

                        </table>

                    </div>
                </section>


                <section class="card">

                    <div class="card-title">
                        Recent realized trades
                    </div>


                    <div class="table-wrap">

                        <table>

                            <thead>
                                <tr>
                                    <th>
                                        Closed
                                    </th>

                                    <th>
                                        Strategy
                                    </th>

                                    <th>
                                        Side
                                    </th>

                                    <th>
                                        P&amp;L
                                    </th>

                                    <th>
                                        R
                                    </th>
                                </tr>
                            </thead>


                            <tbody
                                id="history-body"
                            ></tbody>

                        </table>

                    </div>
                </section>

            </div>
        </div>


        <aside class="stack">

            <section class="card">

                <div class="card-title">
                    Decision state
                </div>


                <div class="row">
                    <span>
                        Diagnostics
                    </span>

                    <b id="diagnostics">
                        —
                    </b>
                </div>


                <div class="row">
                    <span>
                        Model
                    </span>

                    <b id="model-state">
                        —
                    </b>
                </div>


                <div class="row">
                    <span>
                        Prediction
                    </span>

                    <b id="prediction">
                        —
                    </b>
                </div>


                <div class="row">
                    <span>
                        Strategy evidence
                    </span>

                    <b id="strategy-name">
                        NO_EMPIRICAL_DATA
                    </b>
                </div>


                <div class="row">
                    <span>
                        Routing reason
                    </span>

                    <b id="routing-reason">
                        —
                    </b>
                </div>


                <div class="row">
                    <span>
                        News gate
                    </span>

                    <b id="news-gate">
                        —
                    </b>
                </div>

            </section>


            <section
                class="card control-only"
            >

                <div class="card-title">
                    Safe runtime controls
                </div>


                <div class="grid two">

                    <label>
                        Trading mode

                        <select
                            class="field"
                            id="setting-mode"
                        >
                            <option value="scalping">
                                Scalping
                            </option>

                            <option value="intraday">
                                Intraday
                            </option>

                            <option value="swing">
                                Swing
                            </option>
                        </select>
                    </label>


                    <label>
                        Risk %

                        <input
                            class="field"
                            id="setting-risk"
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                        >
                    </label>


                    <label>
                        Max spread points

                        <input
                            class="field"
                            id="setting-spread"
                            type="number"
                            min="1"
                            step="1"
                        >
                    </label>


                    <label>
                        Minimum RR

                        <input
                            class="field"
                            id="setting-rr"
                            type="number"
                            min="1"
                            max="10"
                            step="0.1"
                        >
                    </label>

                </div>


                <div class="section controls">

                    <button
                        class="btn"
                        id="toggle-auto"
                        type="button"
                    >
                        Auto Trade
                    </button>


                    <button
                        class="btn"
                        id="toggle-paper"
                        type="button"
                    >
                        Paper Mode
                    </button>


                    <button
                        class="btn"
                        id="toggle-news"
                        type="button"
                    >
                        USD HIGH News Filter
                    </button>


                    <button
                        class="btn good"
                        id="save-settings"
                        type="button"
                    >
                        Save settings
                    </button>

                </div>


                <div
                    class="muted section"
                    id="settings-msg"
                ></div>

            </section>


            <section class="card">

                <div class="card-title">
                    Manual news schedule
                </div>


                <div
                    class="news-list"
                    id="news-list"
                ></div>


                <div
                    class="control-only section grid two"
                >

                    <label>
                        Day

                        <select
                            class="field"
                            id="news-day"
                        >
                            <option>
                                Monday
                            </option>

                            <option>
                                Tuesday
                            </option>

                            <option>
                                Wednesday
                            </option>

                            <option>
                                Thursday
                            </option>

                            <option>
                                Friday
                            </option>

                            <option>
                                Daily
                            </option>
                        </select>
                    </label>


                    <label>
                        UTC time

                        <input
                            class="field"
                            id="news-time"
                            type="time"
                            value="13:30"
                        >
                    </label>


                    <label
                        style="grid-column:1/-1"
                    >
                        Name

                        <input
                            class="field"
                            id="news-name"
                            maxlength="120"
                            placeholder="Operator-entered event"
                        >
                    </label>


                    <label>
                        Currency

                        <input
                            class="field"
                            id="news-currency"
                            value="USD"
                            maxlength="12"
                        >
                    </label>


                    <label>
                        Impact

                        <select
                            class="field"
                            id="news-impact"
                        >
                            <option>
                                HIGH
                            </option>

                            <option>
                                MEDIUM
                            </option>

                            <option>
                                LOW
                            </option>
                        </select>
                    </label>


                    <button
                        class="btn"
                        id="news-add"
                        type="button"
                        style="grid-column:1/-1"
                    >
                        Add manual event
                    </button>

                </div>
            </section>


            <section
                class="card control-only"
            >

                <div class="card-title">
                    Emergency control
                </div>


                <button
                    class="btn danger"
                    id="panic-close"
                    type="button"
                >
                    Emergency close all
                    &amp; halt new entries
                </button>


                <div class="muted section">
                    No one-click trade button exists.
                    New risk must pass the engine's
                    validated execution pipeline.
                </div>

            </section>

        </aside>

    </div>


    <div class="footer">
        Dashboard is a monitoring/control surface,
        not a signal generator.
        General news sentiment is display-only;
        execution news blocking is USD HIGH only.
    </div>

</div>


<script nonce="{{NONCE}}">
'use strict';


const $ = (
    id
) => (
    document.getElementById(
        id
    )
);


const state = {
    status: null,

    chart: null,

    eventSource: null,

    symbol: '',

    timeframe: 'M5',

    settingsDirty: false
};


function finite(
    value
) {
    const number = Number(
        value
    );

    return (
        Number.isFinite(
            number
        )
        ? number
        : null
    );
}


function money(
    value
) {
    const number = finite(
        value
    );

    if (
        number === null
    ) {
        return '—';
    }

    return (
        new Intl.NumberFormat(
            undefined,
            {
                style: 'currency',
                currency: 'USD'
            }
        ).format(
            number
        )
    );
}


function num(
    value,
    digits = 2
) {
    const number = finite(
        value
    );

    return (
        number === null
        ? '—'
        : number.toFixed(
            digits
        )
    );
}


function text(
    node,
    value
) {
    if (!node) {
        return;
    }

    node.textContent = (
        value === null
        || value === undefined
        || value === ''
    )
        ? '—'
        : String(
            value
        );
}


function setClass(
    node,
    className
) {
    if (!node) {
        return;
    }

    node.classList.remove(
        'status-good',
        'status-bad',
        'status-warn'
    );

    if (className) {
        node.classList.add(
            className
        );
    }
}


function clearNode(
    node
) {
    while (
        node
        && node.firstChild
    ) {
        node.removeChild(
            node.firstChild
        );
    }
}


function makeCell(
    value
) {
    const cell = (
        document.createElement(
            'td'
        )
    );

    cell.textContent = (
        value === null
        || value === undefined
    )
        ? '—'
        : String(
            value
        );

    return cell;
}


async function requestJSON(
    url,
    options = {}
) {
    const response = await fetch(
        url,
        {
            credentials: (
                'same-origin'
            ),

            headers: {
                'Content-Type': (
                    'application/json'
                ),

                ...(
                    options.headers
                    || {}
                )
            },

            ...options
        }
    );


    let body = {};

    try {
        body = await response.json();

    } catch (_) {
        body = {};
    }


    if (!response.ok) {
        throw new Error(
            body.error
            || body.reason
            || `HTTP ${response.status}`
        );
    }

    return body;
}


class CanvasChart {

    constructor(
        canvasId
    ) {
        this.canvas = $(
            canvasId
        );

        this.ctx = (
            this.canvas.getContext(
                '2d'
            )
        );


        this.candles = [];

        this.levels = {};

        this.trades = [];

        this.sweeps = [];

        this.mss = [];


        this.bidPrice = null;

        this.askPrice = null;


        // ============================================================
        // QUIET DEFAULTS
        // ============================================================

        this.showOverlayOB = false;

        this.showOverlayTrend = false;

        this.showOverlayPos = true;

        this.showVolumeProfile = false;

        this.showEMA = false;

        this.showStructureEvents = true;

        this.maxStructureMarkers = 5;


        this.padding = {
            left: 10,
            right: 74,
            top: 18,
            bottom: 28
        };


        this.resize = (
            this.resize.bind(
                this
            )
        );


        window.addEventListener(
            'resize',
            this.resize
        );


        this.resize();
    }


    setData(
        payload
    ) {
        this.candles = (
            Array.isArray(
                payload.candles
            )
            ? payload.candles
            : []
        );


        this.levels = (
            payload.levels
            || {}
        );


        this.trades = (
            Array.isArray(
                payload.trades
            )
            ? payload.trades
            : []
        );


        this.sweeps = (
            Array.isArray(
                payload.sweeps
            )
            ? payload.sweeps.slice(
                -this.maxStructureMarkers
            )
            : []
        );


        this.mss = (
            Array.isArray(
                payload.mss
            )
            ? payload.mss.slice(
                -this.maxStructureMarkers
            )
            : []
        );


        this.draw();
    }


    setQuote(
        bid,
        ask
    ) {
        this.bidPrice = finite(
            bid
        );

        this.askPrice = finite(
            ask
        );

        this.draw();
    }


    resize() {
        const rect = (
            this.canvas
            .getBoundingClientRect()
        );


        const dpr = (
            window.devicePixelRatio
            || 1
        );


        this.width = Math.max(
            320,
            Math.round(
                rect.width
            )
        );


        this.height = Math.max(
            300,
            Math.round(
                rect.height
            )
        );


        this.canvas.width = (
            Math.round(
                this.width
                * dpr
            )
        );


        this.canvas.height = (
            Math.round(
                this.height
                * dpr
            )
        );


        this.ctx.setTransform(
            dpr,
            0,
            0,
            dpr,
            0,
            0
        );


        this.draw();
    }


    visible() {
        return (
            this.candles.slice(
                -Math.min(
                    140,
                    this.candles.length
                )
            )
        );
    }


    range() {
        const bars = (
            this.visible()
        );


        if (!bars.length) {
            return {
                min: 0,
                max: 1
            };
        }


        let minPrice = Math.min(
            ...bars.map(
                candle => Number(
                    candle.low
                )
            )
        );


        let maxPrice = Math.max(
            ...bars.map(
                candle => Number(
                    candle.high
                )
            )
        );


        const extras = [];


        if (
            this.showOverlayPos
        ) {
            this.trades.forEach(
                trade => {

                    [
                        'entry',
                        'sl',
                        'tp'
                    ].forEach(
                        key => {

                            const value = finite(
                                trade[
                                    key
                                ]
                            );

                            if (
                                value !== null
                            ) {
                                extras.push(
                                    value
                                );
                            }
                        }
                    );
                }
            );
        }


        [
            this.bidPrice,
            this.askPrice
        ].forEach(
            value => {

                if (
                    finite(
                        value
                    )
                    !== null
                ) {
                    extras.push(
                        Number(
                            value
                        )
                    );
                }
            }
        );


        extras.forEach(
            value => {

                if (
                    value < minPrice
                ) {
                    minPrice = value;
                }

                if (
                    value > maxPrice
                ) {
                    maxPrice = value;
                }
            }
        );


        const padding = Math.max(
            (
                maxPrice
                - minPrice
            )
            * 0.08,

            Math.abs(
                maxPrice
            )
            * 0.0005,

            1e-8
        );


        return {
            min: (
                minPrice
                - padding
            ),

            max: (
                maxPrice
                + padding
            )
        };
    }


    y(
        price,
        range
    ) {
        const top = (
            this.padding.top
        );


        const bottom = (
            this.height
            - this.padding.bottom
        );


        return (
            bottom
            - (
                (
                    price
                    - range.min
                )
                / (
                    range.max
                    - range.min
                    || 1
                )
            )
            * (
                bottom
                - top
            )
        );
    }


    x(
        index,
        count
    ) {
        const left = (
            this.padding.left
        );


        const right = (
            this.width
            - this.padding.right
        );


        const width = (
            (
                right
                - left
            )
            / Math.max(
                count,
                1
            )
        );


        return (
            left
            + index
            * width
            + width
            / 2
        );
    }


    format(
        price
    ) {
        if (
            Math.abs(
                price
            )
            >= 1000
        ) {
            return price.toFixed(
                2
            );
        }


        if (
            Math.abs(
                price
            )
            >= 100
        ) {
            return price.toFixed(
                3
            );
        }


        if (
            Math.abs(
                price
            )
            >= 10
        ) {
            return price.toFixed(
                4
            );
        }


        return price.toFixed(
            5
        );
    }


    line(
        price,
        label,
        color,
        range,
        dashed = false
    ) {
        const value = finite(
            price
        );


        if (
            value === null
            || value < range.min
            || value > range.max
        ) {
            return;
        }


        const y = this.y(
            value,
            range
        );


        const right = (
            this.width
            - this.padding.right
        );


        this.ctx.save();


        this.ctx.strokeStyle = (
            color
        );

        this.ctx.lineWidth = (
            1
        );


        if (dashed) {
            this.ctx.setLineDash(
                [
                    4,
                    4
                ]
            );
        }


        this.ctx.beginPath();

        this.ctx.moveTo(
            this.padding.left,
            y
        );

        this.ctx.lineTo(
            right,
            y
        );

        this.ctx.stroke();


        this.ctx.setLineDash(
            []
        );


        this.ctx.fillStyle = (
            color
        );

        this.ctx.font = (
            '10px Outfit'
        );

        this.ctx.textAlign = (
            'left'
        );


        this.ctx.fillText(
            `${label} ${this.format(value)}`,
            right + 5,
            y + 3
        );


        this.ctx.restore();
    }


    drawGrid(
        range
    ) {
        const right = (
            this.width
            - this.padding.right
        );


        const bottom = (
            this.height
            - this.padding.bottom
        );


        this.ctx.save();


        this.ctx.strokeStyle = (
            'rgba(142,160,185,.12)'
        );

        this.ctx.fillStyle = (
            '#8ea0b9'
        );

        this.ctx.font = (
            '10px Outfit'
        );


        for (
            let index = 0;
            index <= 5;
            index += 1
        ) {
            const y = (
                this.padding.top
                + (
                    bottom
                    - this.padding.top
                )
                * (
                    index
                    / 5
                )
            );


            const price = (
                range.max
                - (
                    range.max
                    - range.min
                )
                * (
                    index
                    / 5
                )
            );


            this.ctx.beginPath();

            this.ctx.moveTo(
                this.padding.left,
                y
            );

            this.ctx.lineTo(
                right,
                y
            );

            this.ctx.stroke();


            this.ctx.fillText(
                this.format(
                    price
                ),
                right + 5,
                y + 3
            );
        }


        this.ctx.restore();
    }


    drawCandles(
        range
    ) {
        const bars = (
            this.visible()
        );


        const right = (
            this.width
            - this.padding.right
        );


        const left = (
            this.padding.left
        );


        const slot = (
            (
                right
                - left
            )
            / Math.max(
                bars.length,
                1
            )
        );


        const bodyWidth = Math.max(
            2,

            Math.min(
                9,
                slot * 0.65
            )
        );


        bars.forEach(
            (
                candle,
                index
            ) => {

                const x = this.x(
                    index,
                    bars.length
                );


                const openY = this.y(
                    Number(
                        candle.open
                    ),
                    range
                );


                const highY = this.y(
                    Number(
                        candle.high
                    ),
                    range
                );


                const lowY = this.y(
                    Number(
                        candle.low
                    ),
                    range
                );


                const closeY = this.y(
                    Number(
                        candle.close
                    ),
                    range
                );


                // ====================================================
                // EXACT CANDLE COLOR POLICY
                // ====================================================

                const isBullish = (
                    Number(
                        candle.close
                    )
                    >= Number(
                        candle.open
                    )
                );


                const color = (
                    isBullish
                    ? '#22c55e'
                    : '#ef4444'
                );


                this.ctx.strokeStyle = (
                    color
                );

                this.ctx.fillStyle = (
                    color
                );

                this.ctx.lineWidth = (
                    1
                );


                this.ctx.beginPath();

                this.ctx.moveTo(
                    x,
                    highY
                );

                this.ctx.lineTo(
                    x,
                    lowY
                );

                this.ctx.stroke();


                const bodyY = Math.min(
                    openY,
                    closeY
                );


                const bodyHeight = Math.max(
                    1.5,

                    Math.abs(
                        closeY
                        - openY
                    )
                );


                this.ctx.fillRect(
                    x
                    - bodyWidth
                    / 2,

                    bodyY,

                    bodyWidth,

                    bodyHeight
                );
            }
        );
    }


    drawEMA(
        range
    ) {
        if (
            !this.showEMA
            || this.visible().length
            < 21
        ) {
            return;
        }


        const bars = (
            this.visible()
        );


        const calculate = (
            period
        ) => {

            const output = [];

            const factor = (
                2
                / (
                    period
                    + 1
                )
            );


            let current = null;


            bars.forEach(
                (
                    candle,
                    index
                ) => {

                    const close = Number(
                        candle.close
                    );


                    if (
                        index
                        === (
                            period
                            - 1
                        )
                    ) {
                        current = (
                            bars
                            .slice(
                                0,
                                period
                            )
                            .reduce(
                                (
                                    total,
                                    bar
                                ) => (
                                    total
                                    + Number(
                                        bar.close
                                    )
                                ),
                                0
                            )
                            / period
                        );

                    } else if (
                        index
                        >= period
                    ) {
                        current = (
                            close
                            * factor
                            + current
                            * (
                                1
                                - factor
                            )
                        );
                    }


                    output.push(
                        current
                    );
                }
            );


            return output;
        };


        const lines = [
            [
                calculate(
                    9
                ),
                'rgba(56,189,248,.75)'
            ],

            [
                calculate(
                    21
                ),
                'rgba(245,158,11,.75)'
            ]
        ];


        lines.forEach(
            (
                [
                    values,
                    color
                ]
            ) => {

                this.ctx.save();

                this.ctx.strokeStyle = (
                    color
                );

                this.ctx.lineWidth = (
                    1
                );

                this.ctx.beginPath();


                let started = false;


                values.forEach(
                    (
                        value,
                        index
                    ) => {

                        if (
                            value === null
                        ) {
                            return;
                        }


                        const x = this.x(
                            index,
                            bars.length
                        );


                        const y = this.y(
                            value,
                            range
                        );


                        if (!started) {
                            this.ctx.moveTo(
                                x,
                                y
                            );

                            started = true;

                        } else {
                            this.ctx.lineTo(
                                x,
                                y
                            );
                        }
                    }
                );


                this.ctx.stroke();

                this.ctx.restore();
            }
        );
    }


    drawVolumeProfile(
        range
    ) {
        if (
            !this.showVolumeProfile
        ) {
            return;
        }


        const bars = (
            this.visible()
        );


        if (!bars.length) {
            return;
        }


        const bins = (
            20
        );


        const volumes = (
            new Array(
                bins
            ).fill(
                0
            )
        );


        const step = (
            (
                range.max
                - range.min
            )
            / bins
        );


        bars.forEach(
            candle => {

                const midpoint = (
                    (
                        Number(
                            candle.high
                        )
                        + Number(
                            candle.low
                        )
                    )
                    / 2
                );


                const index = Math.max(
                    0,

                    Math.min(
                        bins - 1,

                        Math.floor(
                            (
                                midpoint
                                - range.min
                            )
                            / (
                                step
                                || 1
                            )
                        )
                    )
                );


                volumes[
                    index
                ] += (
                    Number(
                        candle.volume
                    )
                    || 0
                );
            }
        );


        const maxVolume = Math.max(
            ...volumes,
            1
        );


        const right = (
            this.width
            - this.padding.right
        );


        this.ctx.save();


        this.ctx.fillStyle = (
            'rgba(56,189,248,.16)'
        );


        volumes.forEach(
            (
                volume,
                index
            ) => {

                const lowerY = this.y(
                    (
                        range.min
                        + index
                        * step
                    ),
                    range
                );


                const upperY = this.y(
                    (
                        range.min
                        + (
                            index
                            + 1
                        )
                        * step
                    ),
                    range
                );


                const width = (
                    (
                        volume
                        / maxVolume
                    )
                    * 85
                );


                this.ctx.fillRect(
                    right
                    - width,

                    Math.min(
                        lowerY,
                        upperY
                    ),

                    width,

                    Math.max(
                        1,

                        Math.abs(
                            upperY
                            - lowerY
                        )
                    )
                );
            }
        );


        this.ctx.restore();
    }


    drawOB(
        range
    ) {
        if (
            !this.showOverlayOB
        ) {
            return;
        }


        const top = finite(
            this.levels.ob_top
        );


        const bottom = finite(
            this.levels.ob_bottom
        );


        if (
            top === null
            || bottom === null
        ) {
            return;
        }


        const firstY = this.y(
            top,
            range
        );


        const secondY = this.y(
            bottom,
            range
        );


        this.ctx.save();


        this.ctx.strokeStyle = (
            'rgba(167,139,250,.65)'
        );


        this.ctx.setLineDash(
            [
                4,
                4
            ]
        );


        this.ctx.strokeRect(
            this.padding.left,

            Math.min(
                firstY,
                secondY
            ),

            (
                this.width
                - this.padding.left
                - this.padding.right
            ),

            Math.abs(
                secondY
                - firstY
            )
        );


        this.ctx.restore();
    }


    drawTrend(
        range
    ) {
        if (
            !this.showOverlayTrend
        ) {
            return;
        }


        const bars = (
            this.visible()
        );


        if (
            bars.length
            < 12
        ) {
            return;
        }


        const first = (
            bars.slice(
                0,
                6
            )
        );


        const last = (
            bars.slice(
                -6
            )
        );


        const firstPrice = (
            first.reduce(
                (
                    total,
                    candle
                ) => (
                    total
                    + Number(
                        candle.close
                    )
                ),
                0
            )
            / first.length
        );


        const lastPrice = (
            last.reduce(
                (
                    total,
                    candle
                ) => (
                    total
                    + Number(
                        candle.close
                    )
                ),
                0
            )
            / last.length
        );


        this.ctx.save();


        this.ctx.strokeStyle = (
            'rgba(56,189,248,.55)'
        );


        this.ctx.setLineDash(
            [
                5,
                4
            ]
        );


        this.ctx.beginPath();


        this.ctx.moveTo(
            this.x(
                2,
                bars.length
            ),
            this.y(
                firstPrice,
                range
            )
        );


        this.ctx.lineTo(
            this.x(
                bars.length
                - 3,
                bars.length
            ),
            this.y(
                lastPrice,
                range
            )
        );


        this.ctx.stroke();

        this.ctx.restore();
    }


    drawStructure(
        range
    ) {
        if (
            !this.showStructureEvents
        ) {
            return;
        }


        const events = [
            ...this.sweeps.map(
                event => ({
                    ...event,
                    label: 'SWEEP'
                })
            ),

            ...this.mss.map(
                event => ({
                    ...event,
                    label: 'MSS'
                })
            )
        ].slice(
            -this.maxStructureMarkers
        );


        const right = (
            this.width
            - this.padding.right
        );


        events.forEach(
            (
                event,
                index
            ) => {

                const price = finite(
                    event.price
                );


                if (
                    price === null
                ) {
                    return;
                }


                const x = (
                    right
                    - 12
                    - (
                        events.length
                        - 1
                        - index
                    )
                    * 58
                );


                const y = this.y(
                    price,
                    range
                );


                this.ctx.save();


                this.ctx.fillStyle = (
                    event.type
                    === 'bullish'
                    ? '#22c55e'
                    : '#ef4444'
                );


                this.ctx.font = (
                    '9px Outfit'
                );


                this.ctx.textAlign = (
                    'center'
                );


                this.ctx.fillText(
                    (
                        `${
                            event.type
                            === 'bullish'
                            ? '▲'
                            : '▼'
                        } ${event.label}`
                    ),

                    x,

                    Math.max(
                        12,

                        Math.min(
                            this.height
                            - 30,
                            y
                        )
                    )
                );


                this.ctx.restore();
            }
        );
    }


    drawPositions(
        range
    ) {
        if (
            !this.showOverlayPos
        ) {
            return;
        }


        this.trades.forEach(
            trade => {

                const side = String(
                    trade.type
                    || trade.action
                    || ''
                ).toUpperCase();


                this.line(
                    trade.entry,
                    `${side} ENTRY`,
                    '#38bdf8',
                    range,
                    false
                );


                this.line(
                    trade.sl,
                    'SL',
                    '#ef4444',
                    range,
                    true
                );


                this.line(
                    trade.tp,
                    'TP',
                    '#22c55e',
                    range,
                    true
                );
            }
        );
    }


    draw() {
        if (
            !this.ctx
            || !this.width
            || !this.height
        ) {
            return;
        }


        this.ctx.clearRect(
            0,
            0,
            this.width,
            this.height
        );


        this.ctx.fillStyle = (
            '#060a11'
        );


        this.ctx.fillRect(
            0,
            0,
            this.width,
            this.height
        );


        if (
            !this.candles.length
        ) {
            this.ctx.fillStyle = (
                '#8ea0b9'
            );

            this.ctx.font = (
                '14px Outfit'
            );

            this.ctx.textAlign = (
                'center'
            );


            this.ctx.fillText(
                'No market data',
                this.width / 2,
                this.height / 2
            );

            return;
        }


        const range = (
            this.range()
        );


        this.drawGrid(
            range
        );


        this.drawVolumeProfile(
            range
        );


        this.drawOB(
            range
        );


        this.drawCandles(
            range
        );


        // EMA is drawn ONCE only.
        this.drawEMA(
            range
        );


        this.drawTrend(
            range
        );


        this.drawStructure(
            range
        );


        this.drawPositions(
            range
        );


        this.line(
            this.bidPrice,
            'BID',
            '#38bdf8',
            range,
            false
        );


        this.line(
            this.askPrice,
            'ASK',
            '#a78bfa',
            range,
            false
        );
    }
}


const chart = (
    new CanvasChart(
        'chart'
    )
);


function updateToggle(
    id,
    enabled
) {
    const element = $(
        id
    );


    if (element) {
        element.classList.toggle(
            'active',
            Boolean(
                enabled
            )
        );
    }
}


function bindChartToggle(
    id,
    property
) {
    $(
        id
    ).addEventListener(
        'click',
        () => {

            chart[
                property
            ] = !chart[
                property
            ];


            updateToggle(
                id,
                chart[
                    property
                ]
            );


            chart.draw();
        }
    );
}


bindChartToggle(
    'toggle-pos',
    'showOverlayPos'
);


bindChartToggle(
    'toggle-structure',
    'showStructureEvents'
);


bindChartToggle(
    'toggle-ob',
    'showOverlayOB'
);


bindChartToggle(
    'toggle-trend',
    'showOverlayTrend'
);


bindChartToggle(
    'toggle-ema',
    'showEMA'
);


bindChartToggle(
    'toggle-vp',
    'showVolumeProfile'
);


updateToggle(
    'toggle-pos',
    chart.showOverlayPos
);


updateToggle(
    'toggle-structure',
    chart.showStructureEvents
);


async function loadChart() {
    if (
        !state.symbol
    ) {
        return;
    }


    try {
        const payload = (
            await requestJSON(
                (
                    '/api/chart'
                    + `?symbol=${
                        encodeURIComponent(
                            state.symbol
                        )
                    }`
                    + `&timeframe=${
                        encodeURIComponent(
                            state.timeframe
                        )
                    }`
                )
            )
        );


        state.chart = (
            payload
        );


        chart.setData(
            payload
        );


        text(
            $(
                'chart-symbol'
            ),
            payload.symbol
            || state.symbol
        );


        text(
            $(
                'chart-tf'
            ),
            payload.timeframe
            || state.timeframe
        );

    } catch (
        error
    ) {
        console.error(
            'chart',
            error
        );
    }
}


function populateSymbols(
    symbols
) {
    const select = $(
        'symbol-select'
    );


    const previous = (
        state.symbol
    );


    clearNode(
        select
    );


    (
        Array.isArray(
            symbols
        )
        ? symbols
        : []
    ).forEach(
        symbol => {

            const option = (
                document.createElement(
                    'option'
                )
            );


            option.value = (
                String(
                    symbol
                )
            );


            option.textContent = (
                String(
                    symbol
                )
            );


            select.appendChild(
                option
            );
        }
    );


    if (
        !state.symbol
        && select.options.length
    ) {
        state.symbol = (
            select.options[
                0
            ].value
        );
    }


    if (
        previous
        && [
            ...select.options
        ].some(
            option => (
                option.value
                === previous
            )
        )
    ) {
        state.symbol = (
            previous
        );
    }


    select.value = (
        state.symbol
    );
}


function renderPositions(
    rows
) {
    const body = $(
        'positions-body'
    );


    clearNode(
        body
    );


    (
        Array.isArray(
            rows
        )
        ? rows
        : []
    ).forEach(
        position => {

            const row = (
                document.createElement(
                    'tr'
                )
            );


            row.append(
                makeCell(
                    position.symbol
                )
            );


            row.append(
                makeCell(
                    position.action
                )
            );


            row.append(
                makeCell(
                    num(
                        position.volume,
                        2
                    )
                )
            );


            row.append(
                makeCell(
                    num(
                        position.entry_price,
                        5
                    )
                )
            );


            row.append(
                makeCell(
                    num(
                        position.sl,
                        5
                    )
                )
            );


            row.append(
                makeCell(
                    num(
                        position.tp,
                        5
                    )
                )
            );


            const pnlCell = (
                makeCell(
                    money(
                        position.pnl
                    )
                )
            );


            setClass(
                pnlCell,

                finite(
                    position.pnl
                )
                > 0
                ? 'status-good'
                : (
                    finite(
                        position.pnl
                    )
                    < 0
                    ? 'status-bad'
                    : ''
                )
            );


            row.append(
                pnlCell
            );


            body.appendChild(
                row
            );
        }
    );


    if (
        !body.children.length
    ) {
        const row = (
            document.createElement(
                'tr'
            )
        );


        const cell = (
            makeCell(
                'No open positions'
            )
        );


        cell.colSpan = (
            7
        );


        row.append(
            cell
        );


        body.appendChild(
            row
        );
    }
}


function renderHistory(
    rows
) {
    const body = $(
        'history-body'
    );


    clearNode(
        body
    );


    (
        Array.isArray(
            rows
        )
        ? rows
        : []
    )
    .slice(
        -50
    )
    .reverse()
    .forEach(
        trade => {

            const row = (
                document.createElement(
                    'tr'
                )
            );


            row.append(
                makeCell(
                    trade.close_time_utc
                    || '—'
                )
            );


            row.append(
                makeCell(
                    trade.strategy_name
                    || '—'
                )
            );


            row.append(
                makeCell(
                    trade.action
                    || '—'
                )
            );


            const pnlCell = (
                makeCell(
                    money(
                        trade.pnl
                    )
                )
            );


            setClass(
                pnlCell,

                finite(
                    trade.pnl
                )
                > 0
                ? 'status-good'
                : (
                    finite(
                        trade.pnl
                    )
                    < 0
                    ? 'status-bad'
                    : ''
                )
            );


            row.append(
                pnlCell
            );


            row.append(
                makeCell(
                    num(
                        trade.r_multiple,
                        2
                    )
                )
            );


            body.appendChild(
                row
            );
        }
    );


    if (
        !body.children.length
    ) {
        const row = (
            document.createElement(
                'tr'
            )
        );


        const cell = (
            makeCell(
                'No realized trades'
            )
        );


        cell.colSpan = (
            5
        );


        row.append(
            cell
        );


        body.appendChild(
            row
        );
    }
}


function applySettings(
    settings
) {
    if (
        !settings
        || state.settingsDirty
    ) {
        return;
    }


    $(
        'setting-mode'
    ).value = (
        settings.trading_mode
        || 'scalping'
    );


    $(
        'setting-risk'
    ).value = (
        finite(
            settings.risk_percent
        )
        ?? 0.05
    );


    $(
        'setting-spread'
    ).value = (
        finite(
            settings.max_spread_points
        )
        ?? 120
    );


    $(
        'setting-rr'
    ).value = (
        finite(
            settings.min_rr_ratio
        )
        ?? 1.5
    );


    $(
        'toggle-auto'
    ).classList.toggle(
        'active',
        Boolean(
            settings.auto_trade_enabled
        )
    );


    $(
        'toggle-paper'
    ).classList.toggle(
        'active',
        Boolean(
            settings.paper_mode
        )
    );


    $(
        'toggle-news'
    ).classList.toggle(
        'active',
        Boolean(
            settings.news_filter_enabled
        )
    );
}


function renderStatus(
    data
) {
    state.status = (
        data
    );


    const connected = (
        Boolean(
            data.connected
        )
    );


    text(
        $(
            'conn-text'
        ),

        connected
        ? 'CONNECTED'
        : 'DISCONNECTED'
    );


    $(
        'conn-dot'
    ).style.background = (
        connected
        ? 'var(--green)'
        : 'var(--red)'
    );


    text(
        $(
            'cycle-line'
        ),

        data.cycle_id
        ? (
            `Cycle ${data.cycle_id}`
            + (
                data.generated_at_utc
                ? ` • ${data.generated_at_utc}`
                : ''
            )
        )
        : (
            'Waiting for immutable '
            + 'engine snapshot…'
        )
    );


    const account = (
        data.account
        || {}
    );


    const spread = (
        data.spread
        || {}
    );


    const settings = (
        data.settings
        || {}
    );


    text(
        $(
            'balance'
        ),
        money(
            account.balance
        )
    );


    text(
        $(
            'equity'
        ),
        money(
            account.equity
        )
    );


    text(
        $(
            'pnl'
        ),
        money(
            account.profit
        )
    );


    text(
        $(
            'bid'
        ),
        num(
            spread.bid,
            5
        )
    );


    text(
        $(
            'ask'
        ),
        num(
            spread.ask,
            5
        )
    );


    text(
        $(
            'spread'
        ),

        (
            spread.current
            === null
            || spread.current
            === undefined
        )
        ? '—'
        : (
            `${num(
                spread.current,
                1
            )} pt`
        )
    );


    text(
        $(
            'mode-pill'
        ),
        String(
            account.mode
            || 'unknown'
        ).toUpperCase()
    );


    text(
        $(
            'regime-pill'
        ),
        (
            `REGIME ${
                data.market_regime
                || 'UNKNOWN'
            }`
        )
    );


    text(
        $(
            'diagnostics'
        ),
        data.diagnostics_status
        || 'UNKNOWN'
    );


    setClass(
        $(
            'diagnostics'
        ),

        data.diagnostics_status
        === 'HEALTHY'
        ? 'status-good'
        : (
            data.diagnostics_status
            === 'UNHEALTHY'
            ? 'status-bad'
            : 'status-warn'
        )
    );


    const model = (
        data.model_status
        || {}
    );


    text(
        $(
            'model-state'
        ),

        model.status
        || model.model_status
        || model.active_version
        || 'NO_VALID_MODEL'
    );


    const prediction = (
        data.prediction
        || {}
    );


    const confidence = (
        finite(
            prediction.confidence
            ?? prediction.probability
        )
    );


    text(
        $(
            'prediction'
        ),

        confidence === null
        ? (
            prediction.source
            || 'NO_VALID_MODEL'
        )
        : (
            `${(
                confidence
                * 100
            ).toFixed(
                1
            )}%`
        )
    );


    const suggestion = (
        data.strategy_suggestion
    );


    if (
        suggestion
        && typeof suggestion
        === 'object'
    ) {
        text(
            $(
                'strategy-name'
            ),
            suggestion.strategy
            || '—'
        );


        text(
            $(
                'routing-reason'
            ),
            suggestion.reason
            || suggestion.source
            || 'EMPIRICAL_DATA'
        );

    } else {
        text(
            $(
                'strategy-name'
            ),
            'NO_EMPIRICAL_DATA'
        );


        text(
            $(
                'routing-reason'
            ),
            (
                'No validated '
                + 'routing evidence'
            )
        );
    }


    const risk = (
        data.risk_status
        || {}
    );


    const newsBlocked = Boolean(
        risk.news_locked
        || prediction.news_locked
    );


    text(
        $(
            'news-gate'
        ),

        newsBlocked
        ? (
            'BLOCKED — USD HIGH'
        )
        : (
            'CLEAR / NO BLOCK'
        )
    );


    setClass(
        $(
            'news-gate'
        ),

        newsBlocked
        ? 'status-bad'
        : 'status-good'
    );


    populateSymbols(
        data.symbols
        || []
    );


    renderPositions(
        data.positions
        || []
    );


    renderHistory(
        data.history
        || []
    );


    applySettings(
        settings
    );
}


async function pollStatus() {
    try {
        const data = (
            await requestJSON(
                '/api/status'
            )
        );


        renderStatus(
            data
        );


        if (
            !state.symbol
            && Array.isArray(
                data.symbols
            )
            && data.symbols.length
        ) {
            state.symbol = String(
                data.symbols[
                    0
                ]
            );
        }

    } catch (
        error
    ) {
        text(
            $(
                'conn-text'
            ),
            'STATUS ERROR'
        );


        $(
            'conn-dot'
        ).style.background = (
            'var(--red)'
        );
    }
}


function connectSSE() {
    if (
        state.eventSource
    ) {
        state.eventSource.close();
    }


    const source = (
        new EventSource(
            '/api/broadcast/stream'
        )
    );


    state.eventSource = (
        source
    );


    source.addEventListener(
        'tick',
        event => {

            try {
                const quote = (
                    JSON.parse(
                        event.data
                    )
                );


                text(
                    $(
                        'bid'
                    ),
                    num(
                        quote.bid,
                        5
                    )
                );


                text(
                    $(
                        'ask'
                    ),
                    num(
                        quote.ask,
                        5
                    )
                );


                text(
                    $(
                        'spread'
                    ),

                    (
                        quote.spread_points
                        === null
                        || quote.spread_points
                        === undefined
                    )
                    ? '—'
                    : (
                        `${num(
                            quote.spread_points,
                            1
                        )} pt`
                    )
                );


                text(
                    $(
                        'pnl'
                    ),
                    money(
                        quote.pnl
                    )
                );


                chart.setQuote(
                    quote.bid,
                    quote.ask
                );

            } catch (_) {
                // malformed SSE ignored
            }
        }
    );


    source.addEventListener(
        'chart_snapshot',
        () => {
            // Snapshot is already consumed
            // by /api/status.
        }
    );


    source.onerror = (
        () => {
            // EventSource reconnects
            // automatically.
        }
    );
}


$(
    'symbol-select'
).addEventListener(
    'change',
    event => {

        state.symbol = (
            event.target.value
        );


        loadChart();
    }
);


$(
    'tf-select'
).addEventListener(
    'change',
    event => {

        state.timeframe = (
            event.target.value
        );


        loadChart();
    }
);


[
    'setting-mode',
    'setting-risk',
    'setting-spread',
    'setting-rr'
].forEach(
    id => {

        $(
            id
        ).addEventListener(
            'change',
            () => {

                state.settingsDirty = (
                    true
                );
            }
        );
    }
);


[
    'toggle-auto',
    'toggle-paper',
    'toggle-news'
].forEach(
    id => {

        $(
            id
        ).addEventListener(
            'click',
            () => {

                state.settingsDirty = (
                    true
                );


                $(
                    id
                ).classList.toggle(
                    'active'
                );
            }
        );
    }
);


$(
    'save-settings'
).addEventListener(
    'click',
    async () => {

        const payload = {
            trading_mode: (
                $(
                    'setting-mode'
                ).value
            ),

            risk_percent: Number(
                $(
                    'setting-risk'
                ).value
            ),

            max_spread_points: Number(
                $(
                    'setting-spread'
                ).value
            ),

            min_rr_ratio: Number(
                $(
                    'setting-rr'
                ).value
            ),

            auto_trade_enabled: (
                $(
                    'toggle-auto'
                ).classList.contains(
                    'active'
                )
            ),

            paper_mode: (
                $(
                    'toggle-paper'
                ).classList.contains(
                    'active'
                )
            ),

            news_filter_enabled: (
                $(
                    'toggle-news'
                ).classList.contains(
                    'active'
                )
            )
        };


        try {
            await requestJSON(
                '/api/settings',
                {
                    method: 'POST',

                    body: JSON.stringify(
                        payload
                    )
                }
            );


            state.settingsDirty = (
                false
            );


            text(
                $(
                    'settings-msg'
                ),
                (
                    'Saved at cycle-safe '
                    + 'configuration source.'
                )
            );


            await pollStatus();

        } catch (
            error
        ) {
            text(
                $(
                    'settings-msg'
                ),
                (
                    `Rejected: ${
                        error.message
                    }`
                )
            );
        }
    }
);


async function loadNews() {
    const container = $(
        'news-list'
    );


    clearNode(
        container
    );


    try {
        const data = (
            await requestJSON(
                '/api/news_schedule'
            )
        );


        const events = (
            Array.isArray(
                data.events
            )
            ? data.events
            : []
        );


        events.forEach(
            (
                event,
                index
            ) => {

                const wrapper = (
                    document.createElement(
                        'div'
                    )
                );


                wrapper.className = (
                    'news-item'
                );


                const title = (
                    document.createElement(
                        'div'
                    )
                );


                // IMPORTANT:
                // never innerHTML.
                title.textContent = (
                    event.name
                    || 'Unnamed event'
                );


                const meta = (
                    document.createElement(
                        'div'
                    )
                );


                meta.className = (
                    'news-meta'
                );


                meta.textContent = (
                    `${
                        event.day
                        || '—'
                    } ${
                        event.time_utc
                        || '—'
                    } UTC`
                    + ` • ${
                        event.currency
                        || '—'
                    }`
                    + ` • ${
                        event.impact
                        || '—'
                    }`
                    + (
                        event.blocking_eligible
                        ? (
                            ' • BLOCKING ELIGIBLE'
                        )
                        : ''
                    )
                );


                wrapper.append(
                    title,
                    meta
                );


                if (
                    location.pathname
                    !== '/broadcast'
                ) {
                    const removeButton = (
                        document.createElement(
                            'button'
                        )
                    );


                    removeButton.type = (
                        'button'
                    );


                    removeButton.className = (
                        'btn'
                    );


                    removeButton.textContent = (
                        'Remove'
                    );


                    removeButton.style.marginTop = (
                        '6px'
                    );


                    removeButton.addEventListener(
                        'click',
                        async () => {

                            try {
                                await requestJSON(
                                    (
                                        '/api/'
                                        + 'news_schedule/'
                                        + 'remove'
                                    ),
                                    {
                                        method: 'POST',

                                        body: JSON.stringify(
                                            {
                                                index
                                            }
                                        )
                                    }
                                );


                                await loadNews();

                            } catch (
                                error
                            ) {
                                console.error(
                                    error
                                );
                            }
                        }
                    );


                    wrapper.append(
                        removeButton
                    );
                }


                container.append(
                    wrapper
                );
            }
        );


        if (
            !events.length
        ) {
            const empty = (
                document.createElement(
                    'div'
                )
            );


            empty.className = (
                'muted'
            );


            empty.textContent = (
                'No manual events configured.'
            );


            container.append(
                empty
            );
        }

    } catch (
        error
    ) {
        const node = (
            document.createElement(
                'div'
            )
        );


        node.className = (
            'status-bad'
        );


        node.textContent = (
            `News schedule unavailable: ${
                error.message
            }`
        );


        container.append(
            node
        );
    }
}


$(
    'news-add'
).addEventListener(
    'click',
    async () => {

        const payload = {
            day: (
                $(
                    'news-day'
                ).value
            ),

            time_utc: (
                $(
                    'news-time'
                ).value
            ),

            name: (
                $(
                    'news-name'
                )
                .value
                .trim()
            ),

            currency: (
                $(
                    'news-currency'
                )
                .value
                .trim()
            ),

            impact: (
                $(
                    'news-impact'
                ).value
            ),

            duration_mins: 30
        };


        if (
            !payload.name
        ) {
            return;
        }


        try {
            await requestJSON(
                '/api/news_schedule/add',
                {
                    method: 'POST',

                    body: JSON.stringify(
                        payload
                    )
                }
            );


            $(
                'news-name'
            ).value = '';


            await loadNews();

        } catch (
            error
        ) {
            console.error(
                error
            );
        }
    }
);


$(
    'panic-close'
).addEventListener(
    'click',
    async () => {

        const confirmed = (
            window.confirm(
                (
                    'Emergency close all '
                    + 'positions and halt '
                    + 'new entries?'
                )
            )
        );


        if (
            !confirmed
        ) {
            return;
        }


        try {
            const result = (
                await requestJSON(
                    '/api/close_all',
                    {
                        method: 'POST',
                        body: '{}'
                    }
                )
            );


            text(
                $(
                    'settings-msg'
                ),

                result.message
                || result.status
                || (
                    'Emergency command '
                    + 'accepted'
                )
            );

        } catch (
            error
        ) {
            text(
                $(
                    'settings-msg'
                ),
                (
                    'Emergency command '
                    + `failed: ${
                        error.message
                    }`
                )
            );
        }
    }
);


function applyBroadcastMode() {
    if (
        location.pathname
        !== '/broadcast'
    ) {
        return;
    }


    document
    .querySelectorAll(
        '.control-only'
    )
    .forEach(
        element => (
            element.remove()
        )
    );
}


async function boot() {
    applyBroadcastMode();


    await pollStatus();


    if (
        state.status
        && Array.isArray(
            state.status.symbols
        )
        && state.status.symbols.length
    ) {
        state.symbol = String(
            state.status.symbols[
                0
            ]
        );


        $(
            'symbol-select'
        ).value = (
            state.symbol
        );
    }


    await Promise.all(
        [
            loadChart(),
            loadNews()
        ]
    );


    connectSSE();


    setInterval(
        pollStatus,
        2000
    );


    setInterval(
        loadChart,
        5000
    );


    setInterval(
        loadNews,
        60000
    );
}


boot();
</script>

</body>
</html>
"""


# Broadcast uses the same safe renderer.
# JavaScript strips every mutation control
# when pathname == /broadcast.
BROADCAST_TEMPLATE = HTML_TEMPLATE