# dashboard/web_dashboard.py
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
from typing import Dict, Any, List
import MetaTrader5 as mt5
from utils.settings_manager import settings_manager

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
            --bg-dark: #070a13;
            --glass-bg: rgba(16, 24, 48, 0.45);
            --glass-border: rgba(255, 255, 255, 0.05);
            --text-primary: #f1f3f9;
            --text-muted: #8b9bb4;
            --color-green: #00f076;
            --color-red: #ff3366;
            --color-gold: #ffcc00;
            --color-blue: #00a8ff;
            --glow-green: rgba(0, 240, 118, 0.15);
            --glow-red: rgba(255, 51, 102, 0.15);
            --glow-blue: rgba(0, 168, 255, 0.15);
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
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 24px 40px;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--glass-border);
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(7, 10, 19, 0.7);
        }

        .logo-section h1 {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: 2px;
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
            font-size: 14px;
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
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.1); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        .dashboard-container {
            display: grid;
            grid-template-columns: 1.2fr 1.6fr 1fr;
            gap: 20px;
            padding: 28px;
            max-width: 1720px;
            margin: 0 auto;
        }

        @media (max-width: 768px) {
            .dashboard-container {
                grid-template-columns: 1fr;
                padding: 12px;
                gap: 12px;
            }
            .card {
                padding: 14px;
                gap: 12px;
            }
            .card-title {
                font-size: 14px;
            }
            .sentiment-grid {
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
            }
            .sentiment-dial-box {
                padding: 8px;
                gap: 6px;
            }
            .dial-label {
                font-size: 11px;
            }
            .dial-svg-container {
                width: 60px;
                height: 34px;
            }
            .dial-svg {
                width: 60px;
                height: 60px;
            }
        }

        .card {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            backdrop-filter: blur(16px);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
            transition: transform 0.3s ease, border-color 0.3s ease;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.1);
        }

        .card-title {
            font-size: 18px;
            font-weight: 600;
            letter-spacing: 1px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 12px;
            color: var(--text-primary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Sentiment dials */
        .sentiment-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
            gap: 16px;
        }

        .sentiment-dial-box {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            text-align: center;
        }

        .dial-label {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
        }

        .dial-svg-container {
            position: relative;
            width: 80px;
            height: 44px;
            overflow: hidden;
        }

        .dial-svg {
            transform: rotate(180deg);
            width: 80px;
            height: 80px;
            position: absolute;
            top: 0;
            left: 0;
        }

        .dial-bg {
            fill: none;
            stroke: rgba(255, 255, 255, 0.08);
            stroke-width: 6;
            stroke-dasharray: 110 220;
            stroke-linecap: round;
        }

        .dial-progress {
            fill: none;
            stroke-width: 6;
            stroke-linecap: round;
            stroke-dasharray: 0 220;
            stroke-dashoffset: 0;
            transition: stroke-dasharray 0.8s ease, stroke 0.5s ease;
        }

        .dial-text {
            position: absolute;
            bottom: 2px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
        }

        .dial-direction {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-top: 2px;
        }

        .bias-indicator {
            display: flex;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.02);
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 14px;
        }

        .bias-indicator span:last-child {
            font-weight: 700;
        }

        /* Settings CSS */
        .settings-grid {
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .setting-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 4px 0;
        }

        .setting-info {
            display: flex;
            flex-direction: column;
        }

        .setting-name {
            font-size: 14px;
            font-weight: 600;
        }

        .setting-desc {
            font-size: 12px;
            color: var(--text-muted);
        }

        /* Toggle Switch */
        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(255, 255, 255, 0.1);
            transition: .3s;
            border-radius: 24px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }

        input:checked + .slider {
            background-color: var(--color-blue);
        }

        input:checked + .slider:before {
            transform: translateX(20px);
        }

        /* Mode Selection Buttons */
        .mode-selector {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            padding: 4px;
        }

        .mode-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 0;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 13px;
        }

        .mode-btn.active {
            background: var(--color-blue);
            color: var(--text-primary);
            box-shadow: 0 4px 12px var(--glow-blue);
        }

        /* Range Slider */
        .range-slider-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .range-slider-container input {
            flex-grow: 1;
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            outline: none;
        }

        .btn-train {
            background: linear-gradient(135deg, var(--color-blue) 0%, #0056b3 100%);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: transform 0.2s, opacity 0.2s;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 15px var(--glow-blue);
        }

        .btn-train:hover {
            transform: translateY(-2px);
        }

        .btn-train:active {
            transform: translateY(0);
        }

        .btn-train:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        /* Volume Panel CSS */
        .volume-stats {
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .rvol-display {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .rvol-value {
            font-size: 24px;
            font-weight: 700;
        }

        .rvol-label {
            font-size: 13px;
            color: var(--text-muted);
        }

        .pressure-bar-container {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .pressure-labels {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            font-weight: 600;
        }

        .pressure-bar-track {
            height: 10px;
            width: 100%;
            background: var(--color-red);
            border-radius: 5px;
            overflow: hidden;
            display: flex;
        }

        .pressure-buy {
            height: 100%;
            background: var(--color-green);
            transition: width 0.5s ease;
        }

        /* Volume Profile POC Chart */
        .vp-chart {
            display: flex;
            flex-direction: column;
            gap: 4px;
            background: rgba(0, 0, 0, 0.2);
            padding: 12px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .vp-bar-row {
            display: flex;
            align-items: center;
            height: 12px;
            font-size: 10px;
            gap: 8px;
        }

        .vp-price {
            width: 50px;
            color: var(--text-muted);
            font-family: monospace;
        }

        .vp-bar-fill {
            height: 60%;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        .vp-bar-row.poc .vp-bar-fill {
            background: var(--color-gold);
            box-shadow: 0 0 8px var(--color-gold);
        }

        .vp-bar-row.poc .vp-price {
            color: var(--color-gold);
            font-weight: 700;
        }

        /* Grid Column Rules & Layout Positions */
        .sentiment-card {
            grid-column: 1;
            grid-row: 1;
        }

        .prediction-card {
            grid-column: 2;
            grid-row: 1;
        }

        .volume-card {
            grid-column: 3;
            grid-row: 1;
        }

        .bottom-section {
            grid-column: 1 / span 3;
            grid-row: 2;
        }

        .prediction-grid-internal {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            align-items: center;
        }

        @media (max-width: 1400px) {
            .dashboard-container {
                grid-template-columns: 1fr 1fr;
            }
            .sentiment-card {
                grid-column: 1;
                grid-row: 1;
            }
            .prediction-card {
                grid-column: 2;
                grid-row: 1;
            }
            .volume-card {
                grid-column: 1 / span 2;
                grid-row: 2;
            }
            .bottom-section {
                grid-column: 1 / span 2;
                grid-row: 3;
            }
        }

        @media (max-width: 1000px) {
            .dashboard-container {
                grid-template-columns: 1fr;
            }
            .sentiment-card, .bottom-section, .volume-card, .prediction-card {
                grid-column: 1 !important;
                grid-row: auto !important;
            }
        }

        @media (max-width: 600px) {
            .prediction-grid-internal {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        @media (max-width: 400px) {
            .prediction-grid-internal {
                grid-template-columns: 1fr;
            }
        }

        /* ── News and Disclaimer Tickers ────────────────────── */
        .news-ribbon-container {
            background: rgba(10, 15, 30, 0.65);
            border-bottom: 1px solid var(--glass-border);
            border-top: 1px solid var(--glass-border);
            display: flex;
            flex-direction: column;
            width: 100%;
            overflow: hidden;
            font-size: 13px;
            backdrop-filter: blur(12px);
            margin-bottom: 15px;
        }

        .news-ticker-row, .disclaimer-ticker-row {
            display: flex;
            align-items: center;
            height: 34px;
            position: relative;
            overflow: hidden;
        }

        .news-ticker-row {
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            background: rgba(255, 255, 255, 0.01);
        }

        .disclaimer-ticker-row {
            background: rgba(255, 51, 102, 0.015);
        }

        .ticker-label {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            z-index: 10;
            background: #0b0e17;
            padding: 0 16px;
            display: flex;
            align-items: center;
            font-weight: 700;
            font-size: 11px;
            letter-spacing: 1.5px;
            color: var(--color-blue);
            border-right: 1px solid var(--glass-border);
            box-shadow: 4px 0 10px rgba(0, 0, 0, 0.4);
        }

        .ticker-label.text-red {
            color: var(--color-red);
        }

        .ticker-wrap {
            width: 100%;
            overflow: hidden;
            padding-left: 115px;
            display: flex;
            align-items: center;
        }

        .ticker-content {
            display: flex;
            white-space: nowrap;
            gap: 0;
            animation: scroll-rtl 90s linear infinite;
        }

        .ticker-item-group {
            display: flex;
            align-items: center;
            gap: 40px;
            padding-right: 40px;
            flex-shrink: 0;
        }

        .ticker-wrap:hover .ticker-content {
            animation-play-state: paused;
        }

        .ticker-item {
            display: inline-flex;
            align-items: center;
            gap: 12px;
            color: var(--text-primary);
        }

        .ticker-dot {
            color: var(--text-muted);
            opacity: 0.5;
            font-weight: bold;
        }

        .ticker-badge {
            font-size: 9px;
            font-weight: 800;
            padding: 2px 6px;
            border-radius: 4px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .ticker-badge.high {
            background: rgba(255, 51, 102, 0.15);
            color: var(--color-red);
            border: 1px solid rgba(255, 51, 102, 0.3);
            box-shadow: 0 0 6px rgba(255, 51, 102, 0.2);
        }

        .ticker-badge.medium {
            background: rgba(255, 204, 0, 0.15);
            color: var(--color-gold);
            border: 1px solid rgba(255, 204, 0, 0.3);
        }

        .ticker-badge.low {
            background: rgba(0, 240, 118, 0.15);
            color: var(--color-green);
            border: 1px solid rgba(0, 240, 118, 0.3);
        }

        @keyframes scroll-rtl {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
        }



        /* ── Config Drawer ─────────────────────────────────── */
        .config-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.55);
            z-index: 900;
            backdrop-filter: blur(4px);
        }
        .config-overlay.open { display: block; }

        .config-drawer {
            position: fixed;
            top: 0;
            right: -420px;
            width: 400px;
            height: 100vh;
            background: rgba(10, 14, 28, 0.97);
            border-left: 1px solid var(--glass-border);
            z-index: 1000;
            padding: 24px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
            transition: right 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: -8px 0 32px rgba(0,0,0,0.5);
        }
        .config-drawer.open { right: 0; }

        .drawer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--glass-border);
        }
        .drawer-header h2 {
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 1px;
            color: var(--text-primary);
        }
        .drawer-close-btn {
            background: rgba(255,255,255,0.07);
            border: 1px solid var(--glass-border);
            border-radius: 10px;
            color: var(--text-muted);
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 18px;
            transition: all 0.2s;
        }
        .drawer-close-btn:hover {
            background: var(--glow-red);
            color: var(--color-red);
            border-color: var(--color-red);
        }

        .gear-btn {
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            color: var(--text-primary);
            width: 42px;
            height: 42px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 18px;
            transition: all 0.25s ease;
        }
        .gear-btn:hover {
            background: var(--glow-blue);
            border-color: var(--color-blue);
            color: var(--color-blue);
            transform: rotate(45deg);
        }

        .table-tabs {
            display: flex;
            gap: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 16px;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 10px 16px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s ease;
        }

        .tab-btn.active {
            color: var(--color-blue);
            border-bottom-color: var(--color-blue);
        }

        .table-container {
            width: 100%;
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th {
            padding: 12px 16px;
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        td {
            padding: 14px 16px;
            font-size: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.02);
        }

        .badge-buy {
            background: rgba(0, 240, 118, 0.1);
            color: var(--color-green);
            padding: 4px 8px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 12px;
        }

        .badge-sell {
            background: rgba(255, 51, 102, 0.1);
            color: var(--color-red);
            padding: 4px 8px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 12px;
        }

        .pnl-positive {
            color: var(--color-green);
            font-weight: 700;
        }

        .pnl-negative {
            color: var(--color-red);
            font-weight: 700;
        }

        /* News Section CSS */
        .news-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: 250px;
            overflow-y: auto;
            padding-right: 4px;
        }

        .news-list::-webkit-scrollbar {
            width: 4px;
        }
        .news-list::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
        }

        .news-item {
            background: rgba(255, 255, 255, 0.01);
            border-radius: 8px;
            padding: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            transition: background 0.2s;
        }

        .news-item:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        .news-title-link {
            color: var(--text-primary);
            text-decoration: none;
            font-size: 13px;
            line-height: 1.4;
            flex-grow: 1;
        }

        .news-title-link:hover {
            color: var(--color-blue);
        }

        .news-badge {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .news-bullish {
            background: rgba(0, 240, 118, 0.15);
            color: var(--color-green);
        }
        .news-bearish {
            background: rgba(255, 51, 102, 0.15);
            color: var(--color-red);
        }
        .news-neutral {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
        }

        .portfolio-overview {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 16px;
            background: rgba(255, 255, 255, 0.01);
            padding: 16px;
            border-radius: 12px;
            margin-bottom: 20px;
        }

        .portfolio-block {
            display: flex;
            flex-direction: column;
            gap: 4px;
            border-left: 1px solid rgba(255, 255, 255, 0.05);
            padding-left: 16px;
        }

        .portfolio-block:first-child {
            border-left: none;
            padding-left: 0;
        }

        .portfolio-val {
            font-size: 20px;
            font-weight: 700;
        }

        .portfolio-lbl {
            font-size: 12px;
            color: var(--text-muted);
        }

        @media (max-width: 1200px) {
            .portfolio-overview {
                grid-template-columns: repeat(3, 1fr);
            }
            .portfolio-block {
                border-left: 1px solid rgba(255, 255, 255, 0.05);
                padding-left: 16px;
            }
            .portfolio-block:nth-child(3n+1) {
                border-left: none;
                padding-left: 0;
            }
        }

        @media (max-width: 600px) {
            .portfolio-overview {
                grid-template-columns: repeat(2, 1fr);
            }
            .portfolio-block {
                border-left: 1px solid rgba(255, 255, 255, 0.05);
                padding-left: 16px;
            }
            .portfolio-block:nth-child(2n+1) {
                border-left: none;
                padding-left: 0;
            }
        }

        .btn-panic {
            background: linear-gradient(135deg, var(--color-red) 0%, #cc0033 100%);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: transform 0.2s, opacity 0.2s;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 15px var(--glow-red);
            margin-top: 12px;
            width: 100%;
        }

        .btn-panic:hover {
            transform: translateY(-2px);
        }

        .btn-panic:active {
            transform: translateY(0);
        }

        .btn-panic:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1 id="main-header">⚡ PULSE VIPER <span style="font-size: 12px; color: var(--color-blue); letter-spacing: 0.5px; border: 1px solid var(--color-blue); padding: 2px 8px; border-radius: 4px;">SMC EA</span></h1>
        </div>
        <div style="display: flex; gap: 12px; align-items: center;">
            <div class="status-badge" id="spread-badge" style="border-color: var(--glass-border);">
                <span id="spread-lbl">SPREAD: --</span>
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

    <!-- News & Disclaimer Ribbon -->
    <div class="news-ribbon-container">
        <!-- RTL news ribbon -->
        <div class="news-ticker-row">
            <div class="ticker-label">NEWS</div>
            <div class="ticker-wrap">
                <div class="ticker-content" id="news-ticker-content">
                    <div class="ticker-item-group">
                        <div class="ticker-item">
                            <span class="ticker-badge low">INFO</span>
                            <span>Waiting for live market news feed...</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <!-- RTL disclaimer ribbon -->
        <div class="disclaimer-ticker-row">
            <div class="ticker-label text-red">NOTICE</div>
            <div class="ticker-wrap">
                <div class="ticker-content" id="disclaimer-ticker-content">
                    <div class="ticker-item-group">
                        <span class="ticker-item">⚠️ DISCLAIMER: Pulse Viper SMC EA is an automated trading tool. Forex trading involves significant risk of loss. Simulated results do not guarantee future returns. Trade responsibly and manage your margin risk.</span>
                        <span class="ticker-item">⚠️ EDUCATION ONLY: All analysis, patterns, and signals generated are for educational purposes. Never risk capital you cannot afford to lose.</span>
                        <span class="ticker-item">⚠️ LEVERAGE WARNING: High leverage can work against you as well as for you. Please verify all settings before enabling live trading.</span>
                    </div>
                    <div class="ticker-item-group">
                        <span class="ticker-item">⚠️ DISCLAIMER: Pulse Viper SMC EA is an automated trading tool. Forex trading involves significant risk of loss. Simulated results do not guarantee future returns. Trade responsibly and manage your margin risk.</span>
                        <span class="ticker-item">⚠️ EDUCATION ONLY: All analysis, patterns, and signals generated are for educational purposes. Never risk capital you cannot afford to lose.</span>
                        <span class="ticker-item">⚠️ LEVERAGE WARNING: High leverage can work against you as well as for you. Please verify all settings before enabling live trading.</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ── Config Overlay ───────────────────────────────── -->
    <div class="config-overlay" id="config-overlay" onclick="toggleConfigDrawer()"></div>

    <!-- ── Config Drawer ────────────────────────────────── -->
    <div class="config-drawer" id="config-drawer">
        <div class="drawer-header">
            <h2>⚙️ Configuration Panel</h2>
            <button class="drawer-close-btn" onclick="toggleConfigDrawer()">✕</button>
        </div>

        <div class="settings-grid">
            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Trading Engine Mode</span>
                    <span class="setting-desc">Select timeframe strategy scope</span>
                </div>
            </div>
            <div class="mode-selector">
                <button class="mode-btn" id="btn-mode-scalping" onclick="setTradingMode('scalping')">Scalping</button>
                <button class="mode-btn active" id="btn-mode-intraday" onclick="setTradingMode('intraday')">Intraday</button>
                <button class="mode-btn" id="btn-mode-swing" onclick="setTradingMode('swing')">Swing</button>
            </div>

            <div class="setting-row" style="margin-top: 8px;">
                <div class="setting-info">
                    <span class="setting-name">Paper Trading (Simulation)</span>
                    <span class="setting-desc">Simulated execution vs live broker deals</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-paper" onchange="toggleSetting('paper_mode')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Compounding Risk Sizing</span>
                    <span class="setting-desc">Scale size based on floating equity</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-compounding" onchange="toggleSetting('compounding_mode')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Hedging Mode</span>
                    <span class="setting-desc">Open concurrent buying and selling trades</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-hedging" onchange="toggleSetting('hedging_mode')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Trailing Stop-Loss</span>
                    <span class="setting-desc">Dynamically lock profit behind price</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-trailing" onchange="toggleSetting('trailing_stop_enabled')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">Break-Even Auto Trigger</span>
                    <span class="setting-desc">Move SL to entry on 1:1 risk expansion</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-breakeven" onchange="toggleSetting('break_even_enabled')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">News Sentiment Filter</span>
                    <span class="setting-desc">Block trades on adverse news</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-news-filter" onchange="toggleSetting('news_filter_enabled')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row">
                <div class="setting-info">
                    <span class="setting-name">AI Self-Learning Filter</span>
                    <span class="setting-desc">Use pattern learner to validate setups</span>
                </div>
                <label class="switch">
                    <input type="checkbox" id="toggle-self-learning" onchange="toggleSetting('self_learning_filter')">
                    <span class="slider"></span>
                </label>
            </div>

            <div class="setting-row" style="border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px; margin-top: 10px;">
                <div class="setting-info">
                    <span class="setting-name">Risk Amount (%)</span>
                    <span class="setting-desc">Per-trade capital risk allocation</span>
                </div>
            </div>
            <div class="range-slider-container">
                <input type="range" id="input-risk" min="0.25" max="5.0" step="0.25" value="1.0" oninput="updateRiskValue(this.value)" onchange="saveRiskSetting(this.value)">
                <span id="lbl-risk-val" style="font-weight: 700; font-size: 15px; width: 40px; text-align: right;">1.0%</span>
            </div>

            <div class="setting-row" style="border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px; margin-top: 10px;">
                <div class="setting-info">
                    <span class="setting-name">Max Daily Trades</span>
                    <span class="setting-desc">Maximum trades allowed per day</span>
                </div>
            </div>
            <div class="range-slider-container">
                <input type="range" id="input-max-daily" min="1" max="10" step="1" value="3" oninput="updateMaxDailyValue(this.value)" onchange="saveMaxDailySetting(this.value)">
                <span id="lbl-max-daily-val" style="font-weight: 700; font-size: 15px; width: 40px; text-align: right;">3</span>
            </div>

            <div class="setting-row" style="border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px; margin-top: 10px;">
                <div class="setting-info">
                    <span class="setting-name">Max Spread (Points)</span>
                    <span class="setting-desc">Block entry if spread exceeds limit</span>
                </div>
                <span id="lbl-spread-limit" style="font-weight: 700; color: var(--color-blue);">450</span>
            </div>
        </div>

        <div style="flex-grow: 1;"></div>

        <button class="btn-train" id="btn-trigger-training" onclick="triggerTraining()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            <span id="train-btn-txt">TRIGGER AI AUTO-TRAIN</span>
        </button>

        <button class="btn-panic" id="btn-panic-close" onclick="panicCloseAll()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            <span>PANIC: CLOSE ALL POSITIONS</span>
        </button>
    </div>

    <div class="dashboard-container">
        <!-- COLUMN 1: SENTIMENT & BIASES -->
        <div class="card sentiment-card">
            <div class="card-title">
                <span>🧠 AI & Technical Sentiment</span>
                <span style="font-size: 12px; color: var(--color-blue);" id="market-regime-txt">RANGING</span>
            </div>
            
            <div class="sentiment-grid">
                <div class="sentiment-dial-box">
                    <span class="dial-label">News</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-news" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-news">0.0</span>
                    </div>
                    <span class="dial-direction" id="dir-news" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">D1</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-d1" cx="40" cy="40" r="35" stroke="var(--color-gold)"></circle>
                        </svg>
                        <span class="dial-text" id="val-d1">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-d1" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">H4</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-h4" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-h4">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-h4" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">H1</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-h1" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-h1">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-h1" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">M30</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-m30" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-m30">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-m30" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">M15</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-m15" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-m15">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-m15" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">M5</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-m5" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-m5">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-m5" style="color: var(--text-muted);">—</span>
                </div>
                <div class="sentiment-dial-box">
                    <span class="dial-label">M1</span>
                    <div class="dial-svg-container">
                        <svg class="dial-svg" width="80" height="80">
                            <circle class="dial-bg" cx="40" cy="40" r="35"></circle>
                            <circle class="dial-progress" id="dial-m1" cx="40" cy="40" r="35" stroke="var(--color-blue)"></circle>
                        </svg>
                        <span class="dial-text" id="val-m1">0%</span>
                    </div>
                    <span class="dial-direction" id="dir-m1" style="color: var(--text-muted);">—</span>
                </div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 8px;">
                <div class="bias-indicator">
                    <span class="dial-label">H1 Structural Bias</span>
                    <span id="lbl-h1-bias" style="color: var(--text-primary);">Neutral</span>
                </div>
                <div class="bias-indicator">
                    <span class="dial-label">M15 Liquidity Sweep</span>
                    <span id="lbl-m15-sweep" style="color: var(--text-primary);">None</span>
                </div>
                <div class="bias-indicator">
                    <span class="dial-label">M5 Structure Shift</span>
                    <span id="lbl-m5-mss" style="color: var(--text-primary);">None</span>
                </div>
            </div>

            <div class="card-title" style="border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 16px; margin-top: 10px; font-size: 16px;">
                <span>📰 Live Gold News Feed</span>
            </div>
            <div class="news-list" id="news-container">
                <div class="dial-label" style="text-align: center; padding: 20px;">Fetching news feed...</div>
            </div>
        </div>

        <!-- COLUMN 2: NEXT PREDICTION CARD -->
        <div class="card prediction-card" id="prediction-card">
            <div class="card-title">
                <span>🎯 Next Trade Prediction</span>
                <span style="font-size: 12px; color: var(--color-blue);" id="pred-session-badges"></span>
            </div>

            <div class="prediction-grid-internal">
                <!-- Col 0: Setup badge -->
                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 10px 16px; background: rgba(0,168,255,0.07); border: 1px solid rgba(0,168,255,0.2); border-radius: 14px; min-width: 110px;">
                    <span class="dial-label">Next Setup</span>
                    <span id="pred-setup" style="font-weight: 700; font-size: 18px; color: var(--color-blue);">Scanning...</span>
                    <span id="pred-symbol" style="font-size: 11px; color: var(--text-muted); font-weight: 600;">—</span>
                </div>

                <!-- Col 1: Live Price -->
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    <div class="portfolio-block">
                        <span class="portfolio-lbl">Bid</span>
                        <span class="portfolio-val" id="pred-bid">—</span>
                    </div>
                    <div class="portfolio-block">
                        <span class="portfolio-lbl">Ask</span>
                        <span class="portfolio-val" id="pred-ask">—</span>
                    </div>
                </div>

                <!-- Col 2: Entry -->
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Entry Price</span>
                    <span class="portfolio-val" id="pred-entry">—</span>
                </div>

                <!-- Col 3: SL -->
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Stop Loss</span>
                    <span class="portfolio-val" style="color: var(--color-red);" id="pred-sl">—</span>
                </div>

                <!-- Col 4: TP -->
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Take Profit</span>
                    <span class="portfolio-val" style="color: var(--color-green);" id="pred-tp">—</span>
                </div>

                <!-- Col 5: Confidence + skip audit -->
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    <div class="portfolio-block">
                        <span class="portfolio-lbl">AI Confidence</span>
                        <span id="pred-confidence" style="font-weight: 700; font-size: 15px;">—</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px;">
                        <span class="dial-label" style="font-size: 10px;">Spread Skips: <span id="skip-spread" style="color: var(--color-gold); font-weight: 700;">0</span></span>
                        <span class="dial-label" style="font-size: 10px;">News Blocks: <span id="skip-news" style="color: var(--color-gold); font-weight: 700;">0</span></span>
                        <span class="dial-label" style="font-size: 10px;">KZ Inactive: <span id="skip-killzone" style="color: var(--color-gold); font-weight: 700;">0</span></span>
                        <span class="dial-label" style="font-size: 10px;">Low Conf: <span id="skip-confidence" style="color: var(--color-gold); font-weight: 700;">0</span></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- COLUMN 3: VOLUME ANALYTICS -->
        <div class="card volume-card">
            <div class="card-title">
                <span>📊 Advanced Volume Analytics</span>
            </div>
            
            <div class="volume-stats">
                <div class="rvol-display">
                    <div class="portfolio-block">
                        <span class="rvol-label">Relative Volume (RVOL)</span>
                        <span class="rvol-value" id="val-rvol">1.00</span>
                    </div>
                    <span id="badge-rvol" class="news-badge news-neutral">NORMAL</span>
                </div>

                <div class="pressure-bar-container">
                    <div class="pressure-labels">
                        <span style="color: var(--color-green)">BUYING PRESSURE</span>
                        <span style="color: var(--color-red)">SELLING PRESSURE</span>
                    </div>
                    <div class="pressure-bar-track">
                        <div class="pressure-buy" id="bar-buy" style="width: 50%;"></div>
                    </div>
                    <div class="pressure-labels" style="font-size: 12px; color: var(--text-muted);">
                        <span id="val-buy">50%</span>
                        <span id="val-sell">50%</span>
                    </div>
                </div>

                <div class="card-title" style="font-size: 15px; border-bottom: none; padding-bottom: 0;">
                    <span>Volume Profile POC Histogram (Last 100 bars)</span>
                </div>
                <div class="vp-chart" id="vp-chart-container">
                    <!-- Dynamic rendering of bins -->
                </div>
            </div>
        </div>

        <!-- BOTTOM COLUMN: ACTIVE TRADES AND HISTORY -->
        <div class="card bottom-section">
            <div class="portfolio-overview">
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Floating Account Equity</span>
                    <span class="portfolio-val" id="val-equity">$10,000.00</span>
                </div>
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Closed Balance</span>
                    <span class="portfolio-val" id="val-balance">$10,000.00</span>
                </div>
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Running Unrealized PnL</span>
                    <span class="portfolio-val" id="val-floating-pnl">$0.00</span>
                </div>
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Margin Level</span>
                    <span class="portfolio-val" id="val-margin-level">N/A</span>
                </div>
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Leverage</span>
                    <span class="portfolio-val" id="val-leverage">N/A</span>
                </div>
                <div class="portfolio-block">
                    <span class="portfolio-lbl">Loop Latency</span>
                    <span class="portfolio-val" id="val-latency">--</span>
                </div>
            </div>

            <div class="table-tabs">
                <button class="tab-btn active" id="tab-active" onclick="switchTab('active')">Active Trades</button>
                <button class="tab-btn" id="tab-history" onclick="switchTab('history')">Trade History</button>
            </div>

            <div class="table-container" id="table-active-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ticket</th>
                            <th>Symbol</th>
                            <th>Action</th>
                            <th>Volume</th>
                            <th>Entry Price</th>
                            <th>Stop Loss</th>
                            <th>Take Profit</th>
                            <th>PnL</th>
                        </tr>
                    </thead>
                    <tbody id="active-positions-tbody">
                        <tr>
                            <td colspan="8" style="text-align: center; color: var(--text-muted);">No active positions.</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="table-container" id="table-history-container" style="display: none;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticket</th>
                            <th>Symbol</th>
                            <th>Action</th>
                            <th>Volume</th>
                            <th>Entry Price</th>
                            <th>Close Price</th>
                            <th>Close Time</th>
                            <th>Reason</th>
                            <th>PnL</th>
                        </tr>
                    </thead>
                    <tbody id="history-positions-tbody">
                        <tr>
                            <td colspan="9" style="text-align: center; color: var(--text-muted);">No trade history recorded.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let currentTab = 'active';

        function updateRiskValue(val) {
            document.getElementById('lbl-risk-val').innerText = parseFloat(val).toFixed(2) + '%';
        }

        function updateMaxDailyValue(val) {
            document.getElementById('lbl-max-daily-val').innerText = parseInt(val);
        }

        async function saveMaxDailySetting(val) {
            sendSettingUpdate({ "max_daily_trades": parseInt(val) });
        }

        function toggleConfigDrawer() {
            const drawer = document.getElementById('config-drawer');
            const overlay = document.getElementById('config-overlay');
            const gearBtn = document.getElementById('gear-toggle-btn');
            const isOpen = drawer.classList.toggle('open');
            overlay.classList.toggle('open', isOpen);
            gearBtn.style.borderColor = isOpen ? 'var(--color-blue)' : 'var(--glass-border)';
            gearBtn.style.color = isOpen ? 'var(--color-blue)' : 'var(--text-primary)';
            gearBtn.style.background = isOpen ? 'var(--glow-blue)' : 'rgba(255,255,255,0.06)';
        }

        // Close drawer on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const drawer = document.getElementById('config-drawer');
                if (drawer.classList.contains('open')) toggleConfigDrawer();
            }
        });

        function adjustTickerSpeed(tickerId, speedPxPerSec = 40) {
            const ticker = document.getElementById(tickerId);
            if (!ticker) return;
            // Use setTimeout to ensure the browser has finished layout calculations
            setTimeout(() => {
                requestAnimationFrame(() => {
                    const groups = ticker.querySelectorAll('.ticker-item-group');
                    if (groups.length >= 2) {
                        const groupWidth = groups[0].getBoundingClientRect().width;
                        if (groupWidth > 0) {
                            const duration = groupWidth / speedPxPerSec;
                            ticker.style.animationDuration = `${duration}s`;
                        }
                    }
                });
            }, 50);
        }

        window.addEventListener('load', () => {
            adjustTickerSpeed('disclaimer-ticker-content', 40);
            adjustTickerSpeed('news-ticker-content', 40);
        });

        window.addEventListener('resize', () => {
            adjustTickerSpeed('disclaimer-ticker-content', 40);
            adjustTickerSpeed('news-ticker-content', 40);
        });

        // Ensure calculations run when custom/Google fonts are loaded and layout shifts occur
        if (document.fonts) {
            document.fonts.ready.then(() => {
                adjustTickerSpeed('disclaimer-ticker-content', 40);
                adjustTickerSpeed('news-ticker-content', 40);
            });
        }

        function switchTab(tab) {
            currentTab = tab;
            document.getElementById('tab-active').classList.toggle('active', tab === 'active');
            document.getElementById('tab-history').classList.toggle('active', tab === 'history');
            
            document.getElementById('table-active-container').style.display = tab === 'active' ? 'block' : 'none';
            document.getElementById('table-history-container').style.display = tab === 'history' ? 'block' : 'none';
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                if (!response.ok) return;
                const data = await response.json();
                updateUI(data);
            } catch (e) {
                console.error("Failed to fetch dashboard updates", e);
            }
        }

        function updateUI(data) {
            // Update Header & Broker Info
            const broker = data.account.broker || "GENERIC";
            const server = data.account.server || "";
            const mode = data.account.mode === "paper" ? "🎮 PAPER TRADING" : "⚠️ LIVE TRADING";
            document.getElementById('broker-name').innerText = `${mode} | Broker: ${broker} (${server})`;
            
            // Update Market Regime & Header Status
            document.getElementById('market-regime-txt').innerText = (data.market_regime || "RANGING").toUpperCase();
            
            // Update Sentiment dials
            updateDial('dial-news', 'val-news', data.sentiment.news, true);
            updateDial('dial-d1', 'val-d1', data.sentiment.d1);
            updateDial('dial-h4', 'val-h4', data.sentiment.h4);
            updateDial('dial-h1', 'val-h1', data.sentiment.h1);
            updateDial('dial-m30', 'val-m30', data.sentiment.m30);
            updateDial('dial-m15', 'val-m15', data.sentiment.m15);
            updateDial('dial-m5', 'val-m5', data.sentiment.m5);
            updateDial('dial-m1', 'val-m1', data.sentiment.m1);

            // Update Next Prediction card
            if (data.prediction) {
                const p = data.prediction;
                const symEl = document.getElementById('pred-symbol');
                const bidEl = document.getElementById('pred-bid');
                const askEl = document.getElementById('pred-ask');
                const setupEl = document.getElementById('pred-setup');
                const entryEl = document.getElementById('pred-entry');
                const slEl = document.getElementById('pred-sl');
                const tpEl = document.getElementById('pred-tp');
                const confEl = document.getElementById('pred-confidence');
                const sessEl = document.getElementById('pred-session-badges');
                if (symEl) symEl.innerText = p.symbol || '—';
                if (bidEl) bidEl.innerText = p.bid ? p.bid.toFixed(2) : '—';
                if (askEl) askEl.innerText = p.ask ? p.ask.toFixed(2) : '—';
                if (setupEl) {
                    setupEl.innerText = p.setup || 'Scanning...';
                    setupEl.style.color = p.action === 'BUY' ? 'var(--color-green)' : (p.action === 'SELL' ? 'var(--color-red)' : 'var(--color-blue)');
                }
                if (entryEl) entryEl.innerText = p.entry ? p.entry.toFixed(5) : '—';
                if (slEl) slEl.innerText = p.sl ? p.sl.toFixed(5) : '—';
                if (tpEl) tpEl.innerText = p.tp ? p.tp.toFixed(5) : '—';
                if (confEl) {
                    const conf = p.confidence || 0;
                    confEl.innerText = `${conf.toFixed(1)}%`;
                    confEl.style.color = conf >= 60 ? 'var(--color-green)' : (conf >= 40 ? 'var(--color-gold)' : 'var(--color-red)');
                }
                if (sessEl && p.active_sessions) {
                    sessEl.innerHTML = p.active_sessions.map(s => `<span style="background: rgba(100,200,255,0.15); border: 1px solid rgba(100,200,255,0.3); border-radius: 6px; padding: 2px 8px; font-size: 11px; margin-left: 4px;">${s}</span>`).join('');
                }
            }

            // Update skip audit counters
            if (data.skipped_stats) {
                const sk = data.skipped_stats;
                const spreadEl = document.getElementById('skip-spread');
                const newsEl = document.getElementById('skip-news');
                const killEl = document.getElementById('skip-killzone');
                const confEl2 = document.getElementById('skip-confidence');
                if (spreadEl) spreadEl.innerText = sk.high_spread || 0;
                if (newsEl) newsEl.innerText = sk.news_filter || 0;
                if (killEl) killEl.innerText = sk.killzone_inactive || 0;
                if (confEl2) confEl2.innerText = sk.low_confidence || 0;
            }

            updateTextIndicator('lbl-h1-bias', data.sentiment.h1_bias_label, data.sentiment.h1);
            updateTextIndicator('lbl-m15-sweep', data.sentiment.m15_sweep_label, data.sentiment.m15);
            updateTextIndicator('lbl-m5-mss', data.sentiment.m5_mss_label, data.sentiment.m5);

            // Update Settings inputs in drawer
            document.getElementById('toggle-paper').checked = data.settings.paper_mode;
            document.getElementById('toggle-compounding').checked = data.settings.compounding_mode;
            document.getElementById('toggle-hedging').checked = data.settings.hedging_mode;
            document.getElementById('toggle-trailing').checked = data.settings.trailing_stop_enabled;
            document.getElementById('toggle-breakeven').checked = data.settings.break_even_enabled;
            if (document.getElementById('toggle-news-filter'))
                document.getElementById('toggle-news-filter').checked = data.settings.news_filter_enabled;
            if (document.getElementById('toggle-self-learning'))
                document.getElementById('toggle-self-learning').checked = data.settings.self_learning_filter;

            // Sync max daily trades slider
            const maxDailyInput = document.getElementById('input-max-daily');
            if (maxDailyInput && document.activeElement !== maxDailyInput) {
                maxDailyInput.value = data.settings.max_daily_trades || 3;
                updateMaxDailyValue(data.settings.max_daily_trades || 3);
            }

            // Sync spread limit display
            const spreadLimitEl = document.getElementById('lbl-spread-limit');
            if (spreadLimitEl && data.settings.max_spread_points)
                spreadLimitEl.innerText = data.settings.max_spread_points;
            
            const riskInput = document.getElementById('input-risk');
            if (document.activeElement !== riskInput) {
                riskInput.value = data.settings.risk_percent;
                updateRiskValue(data.settings.risk_percent);
            }

            // Update Mode buttons
            const activeMode = data.settings.trading_mode || "intraday";
            document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.getElementById(`btn-mode-${activeMode}`);
            if (activeBtn) activeBtn.classList.add('active');

            // Update Volume Panel
            const rvol = data.volume.rvol || 1.0;
            document.getElementById('val-rvol').innerText = rvol.toFixed(2);
            const badge = document.getElementById('badge-rvol');
            badge.innerText = rvol > 1.5 ? "EXPANDING" : "NORMAL";
            badge.className = `news-badge ${rvol > 1.5 ? 'news-bearish' : 'news-neutral'}`;
            
            // Buy Sell Pressure
            const buy = data.volume.buy_pressure || 50.0;
            const sell = data.volume.sell_pressure || 50.0;
            document.getElementById('bar-buy').style.width = `${buy}%`;
            document.getElementById('val-buy').innerText = `${buy.toFixed(0)}%`;
            document.getElementById('val-sell').innerText = `${sell.toFixed(0)}%`;

            // Volume Profile Profile Chart
            renderVolumeProfile(data.volume.profile);

            // Update Portfolio Block
            document.getElementById('val-equity').innerText = `$${parseFloat(data.account.equity).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
            document.getElementById('val-balance').innerText = `$${parseFloat(data.account.balance).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
            const fpnl = data.account.profit;
            const fpnlEl = document.getElementById('val-floating-pnl');
            fpnlEl.innerText = `${fpnl >= 0 ? '+' : ''}$${parseFloat(fpnl).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
            fpnlEl.className = `portfolio-val ${fpnl > 0 ? 'pnl-positive' : (fpnl < 0 ? 'pnl-negative' : '')}`;

            // Update Margin level, leverage, latency
            document.getElementById('val-margin-level').innerText = data.margin_level || "N/A";
            document.getElementById('val-leverage').innerText = data.leverage || "N/A";
            document.getElementById('val-latency').innerText = data.latency_ms !== undefined ? `${data.latency_ms}ms` : "N/A";

            // Update spread badge
            const spreadBadge = document.getElementById('spread-badge');
            const spreadLbl = document.getElementById('spread-lbl');
            if (data.spread && data.spread.current !== null) {
                spreadLbl.innerText = `SPREAD: ${data.spread.current} pt (Max: ${data.spread.max_limit})`;
                if (data.spread.exceeded) {
                    spreadBadge.style.borderColor = 'var(--color-red)';
                    spreadBadge.style.color = 'var(--color-red)';
                    spreadBadge.style.background = 'rgba(255, 51, 102, 0.15)';
                    spreadBadge.style.boxShadow = '0 0 10px rgba(255, 51, 102, 0.2)';
                } else {
                    spreadBadge.style.borderColor = 'var(--glass-border)';
                    spreadBadge.style.color = 'var(--text-primary)';
                    spreadBadge.style.background = 'var(--glass-bg)';
                    spreadBadge.style.boxShadow = 'none';
                }
            } else {
                spreadLbl.innerText = 'SPREAD: N/A';
                spreadBadge.style.borderColor = 'var(--glass-border)';
                spreadBadge.style.color = 'var(--text-primary)';
                spreadBadge.style.background = 'var(--glass-bg)';
                spreadBadge.style.boxShadow = 'none';
            }

            // Update Tables
            updateActivePositionsTable(data.positions);
            updateHistoryPositionsTable(data.history);

            // Update News Feed
            updateNewsFeed(data.sentiment.news_articles);

            // Update Training Button
            const trainBtn = document.getElementById('btn-trigger-training');
            const trainTxt = document.getElementById('train-btn-txt');
            if (data.training_status === "training") {
                trainBtn.disabled = true;
                trainTxt.innerText = "TRAINING IN PROGRESS...";
            } else {
                trainBtn.disabled = false;
                trainTxt.innerText = "TRIGGER AI AUTO-TRAIN";
            }
        }

        function updateDial(id, valId, score, isNews = false) {
            const dial = document.getElementById(id);
            const valEl = document.getElementById(valId);
            if (!dial || !valEl) return;
            
            // Score range [-1.0, 1.0]. Normalize to 0-100%
            const percent = ((score + 1.0) / 2.0) * 100;
            if (isNews) {
                valEl.innerText = score.toFixed(2);
            } else {
                valEl.innerText = `${Math.round(score * 100)}%`;
            }
            
            // Speedometer: half-circle arch (110 units = full 180deg)
            // stroke-dasharray: "filled_part 220"
            const filled = (percent / 100) * 110;
            dial.style.strokeDasharray = `${filled} 220`;
            dial.style.strokeDashoffset = 0;
            
            // Color mapping based on score
            let color;
            if (score > 0.15) {
                color = "var(--color-green)";
            } else if (score < -0.15) {
                color = "var(--color-red)";
            } else {
                color = "var(--text-muted)";
            }
            dial.style.stroke = color;

            // Update direction label
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

        function updateTextIndicator(id, label, score) {
            const el = document.getElementById(id);
            el.innerText = label || "Neutral";
            if (score > 0.15) {
                el.style.color = "var(--color-green)";
                el.style.textShadow = "0 0 5px var(--glow-green)";
            } else if (score < -0.15) {
                el.style.color = "var(--color-red)";
                el.style.textShadow = "0 0 5px var(--glow-red)";
            } else {
                el.style.color = "var(--text-primary)";
                el.style.textShadow = "none";
            }
        }

        function renderVolumeProfile(profile) {
            const container = document.getElementById('vp-chart-container');
            if (!profile || !profile.bin_edges || profile.bin_edges.length === 0) {
                container.innerHTML = `<div class="dial-label" style="text-align: center; padding: 10px;">Loading profile...</div>`;
                return;
            }

            const volumes = profile.bin_volumes;
            const edges = profile.bin_edges;
            const maxVol = Math.max(...volumes, 1.0);
            const pocPrice = profile.poc_price;

            let html = "";
            // Reverse so higher prices are at the top of the chart
            for (let i = volumes.length - 1; i >= 0; i--) {
                const binPriceLow = edges[i];
                const binPriceHigh = edges[i+1];
                const binMid = (binPriceLow + binPriceHigh) / 2.0;
                const isPoc = Math.abs(binMid - pocPrice) < (binPriceHigh - binPriceLow)/2.0;
                const widthPct = (volumes[i] / maxVol) * 100;
                
                html += `
                <div class="vp-bar-row ${isPoc ? 'poc' : ''}">
                    <span class="vp-price">${binMid.toFixed(2)}</span>
                    <div class="vp-bar-fill" style="width: ${widthPct}%;"></div>
                </div>
                `;
            }
            container.innerHTML = html;
        }

        function updateActivePositionsTable(positions) {
            const tbody = document.getElementById('active-positions-tbody');
            if (!positions || positions.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No active positions.</td></tr>`;
                return;
            }

            let html = "";
            positions.forEach(pos => {
                const actionBadge = pos.action === "BUY" ? `<span class="badge-buy">BUY</span>` : `<span class="badge-sell">SELL</span>`;
                const pnlClass = pos.pnl > 0 ? "pnl-positive" : (pos.pnl < 0 ? "pnl-negative" : "");
                const pnlStr = (pos.pnl >= 0 ? "+" : "") + pos.pnl.toFixed(2);
                
                const slStr = pos.sl_usd !== null && pos.sl_usd !== undefined
                    ? `$${pos.sl.toFixed(2)} <span style="font-size: 11px; color: var(--color-red); opacity: 0.85;">(${pos.sl_usd >= 0 ? '+' : ''}${pos.sl_usd.toFixed(2)})</span>`
                    : `$${pos.sl.toFixed(2)}`;
                    
                const tpStr = pos.tp_usd !== null && pos.tp_usd !== undefined
                    ? `$${pos.tp.toFixed(2)} <span style="font-size: 11px; color: var(--color-green); opacity: 0.85;">(+${pos.tp_usd.toFixed(2)})</span>`
                    : `$${pos.tp.toFixed(2)}`;

                html += `
                <tr>
                    <td>#${pos.id}</td>
                    <td>${pos.symbol}</td>
                    <td>${actionBadge}</td>
                    <td>${pos.volume.toFixed(2)}</td>
                    <td>$${pos.entry_price.toFixed(2)}</td>
                    <td>${slStr}</td>
                    <td>${tpStr}</td>
                    <td class="${pnlClass}">$${pnlStr}</td>
                </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function updateHistoryPositionsTable(history) {
            const tbody = document.getElementById('history-positions-tbody');
            if (!history || history.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No trade history recorded.</td></tr>`;
                return;
            }

            let html = "";
            // Show latest trades first
            [...history].reverse().forEach(pos => {
                const actionBadge = pos.action === "BUY" ? `<span class="badge-buy">BUY</span>` : `<span class="badge-sell">SELL</span>`;
                const pnlClass = pos.pnl > 0 ? "pnl-positive" : (pos.pnl < 0 ? "pnl-negative" : "");
                const pnlStr = (pos.pnl >= 0 ? "+" : "") + pos.pnl.toFixed(2);
                
                // Format time: remove milliseconds and strip long strings
                const timeStr = pos.close_time ? pos.close_time.split('.')[0] : "";
                
                html += `
                <tr>
                    <td>#${pos.id}</td>
                    <td>${pos.symbol}</td>
                    <td>${actionBadge}</td>
                    <td>${pos.volume.toFixed(2)}</td>
                    <td>$${pos.entry_price.toFixed(2)}</td>
                    <td>$${pos.close_price.toFixed(2)}</td>
                    <td style="font-size: 12px; color: var(--text-muted);">${timeStr}</td>
                    <td>${pos.close_reason}</td>
                    <td class="${pnlClass}">$${pnlStr}</td>
                </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function isHighImpactUSANews(art) {
            const title = (art.title || "").toLowerCase();
            const desc = (art.description || "").toLowerCase();
            const sentiment = art.sentiment || 0;
            
            // US/USA Keywords
            const usKeywords = ['us', 'usa', 'fed', 'federal reserve', 'dollar', 'usd', 'powell', 'inflation', 'cpi', 'nfp', 'nonfarm', 'treasury', 'fomc', 'yields', 'america', 'american', 'yellen', 'lagarde', 'dxy'];
            
            // High Impact Keywords
            const highImpactKeywords = ['fed', 'fomc', 'powell', 'cpi', 'inflation', 'nfp', 'nonfarm', 'interest rate', 'rates', 'gdp', 'meeting', 'rate cut', 'hike', 'hikes', 'unemployment', 'employment', 'payrolls', 'pmi', 'retail sales', 'hawkish', 'dovish'];
            
            // Match US
            const isUS = usKeywords.some(kw => title.includes(kw) || desc.includes(kw));
            if (!isUS) return false;
            
            // Match High Impact
            const isHigh = highImpactKeywords.some(kw => title.includes(kw) || desc.includes(kw)) || Math.abs(sentiment) >= 0.35;
            return isHigh;
        }

        function updateNewsFeed(articles) {
            const container = document.getElementById('news-container');
            const ticker = document.getElementById('news-ticker-content');
            
            if (!articles || articles.length === 0) {
                if (container) {
                    container.innerHTML = `<div class="dial-label" style="text-align: center; padding: 20px;">No news alerts available.</div>`;
                }
                if (ticker) {
                    ticker.innerHTML = `
                        <div class="ticker-item-group">
                            <div class="ticker-item">
                                <span class="ticker-badge low">INFO</span>
                                <span>No news alerts available.</span>
                            </div>
                        </div>
                    `;
                }
                return;
            }

            const filteredArticles = articles.filter(isHighImpactUSANews);

            if (filteredArticles.length === 0) {
                if (container) {
                    container.innerHTML = `<div class="dial-label" style="text-align: center; padding: 20px; font-size: 13px;">No high-impact US news alerts.</div>`;
                }
                if (ticker) {
                    ticker.innerHTML = `
                        <div class="ticker-item-group">
                            <div class="ticker-item">
                                <span class="ticker-badge low">INFO</span>
                                <span>No high-impact US news alerts.</span>
                            </div>
                        </div>
                    `;
                }
                return;
            }

            // Update traditional news card container
            if (container) {
                let html = "";
                filteredArticles.forEach(art => {
                    const sentiment = art.sentiment;
                    let badgeClass = "news-neutral";
                    let sentimentLabel = "NEUT";
                    if (sentiment > 0.15) {
                        badgeClass = "news-bullish";
                        sentimentLabel = "BULL";
                    } else if (sentiment < -0.15) {
                        badgeClass = "news-bearish";
                        sentimentLabel = "BEAR";
                    }
                    
                    html += `
                    <div class="news-item" style="display: flex; flex-direction: column; gap: 4px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 8px;">
                            <a href="${art.link}" target="_blank" class="news-title-link" style="font-weight: 600; text-decoration: none;">${art.title}</a>
                            <span class="news-badge ${badgeClass}">${sentimentLabel}</span>
                        </div>
                        ${art.description ? `<p style="font-size: 12px; color: var(--text-muted); margin: 2px 0 0 0; line-height: 1.4;">${art.description}</p>` : ''}
                    </div>
                    `;
                });
                container.innerHTML = html;
            }

            // Update scrolling news ticker ribbon under header
            if (ticker) {
                function getNewsImpact(art) {
                    const title = art.title.toLowerCase();
                    const desc = (art.description || "").toLowerCase();
                    const sent = Math.abs(art.sentiment || 0);
                    const highKeywords = ['fed', 'fomc', 'powell', 'cpi', 'inflation', 'nfp', 'nonfarm', 'interest rate', 'rates', 'gdp', 'meeting', 'rate cut', 'hike', 'hikes', 'unemployment', 'employment', 'payrolls', 'pmi', 'retail sales', 'hawkish', 'dovish'];
                    const medKeywords = ['gold', 'xau', 'dollar', 'usd', 'bond', 'yield', 'retail sales', 'pmi', 'central bank', 'stocks', 'jobless', 'claims'];
                    
                    if (highKeywords.some(kw => title.includes(kw) || desc.includes(kw)) || sent >= 0.6) {
                        return 'HIGH';
                    } else if (medKeywords.some(kw => title.includes(kw) || desc.includes(kw)) || sent >= 0.25) {
                        return 'MEDIUM';
                    }
                    return 'LOW';
                }

                let tickerHtml = "";
                filteredArticles.forEach(art => {
                    const impact = getNewsImpact(art);
                    let badgeClass = "low";
                    if (impact === "HIGH") badgeClass = "high";
                    else if (impact === "MEDIUM") badgeClass = "medium";
                    
                    let descTruncated = "";
                    if (art.description && art.description.trim()) {
                        let descText = art.description.trim();
                        if (descText.length > 140) {
                            descText = descText.substring(0, 140) + "...";
                        }
                        descTruncated = `<span style="color: var(--text-muted); font-size: 11px; margin-left: 4px; font-weight: normal;">(${descText})</span>`;
                    }
                    
                    tickerHtml += `
                    <div class="ticker-item">
                        <span class="ticker-badge ${badgeClass}">${impact}</span>
                        <a href="${art.link}" target="_blank" class="news-title-link" style="color: var(--text-primary); text-decoration: none; font-weight: 600;">${art.title}</a>
                        ${descTruncated}
                        <span class="ticker-dot">•</span>
                    </div>
                    `;
                });

                // Duplicate content groups for seamless loops (exactly 2 groups for -50% translate scroll-rtl keyframe)
                ticker.innerHTML = `
                    <div class="ticker-item-group">${tickerHtml}</div>
                    <div class="ticker-item-group">${tickerHtml}</div>
                `;

                // Recalculate duration dynamically to maintain 40px/s speed
                adjustTickerSpeed('news-ticker-content', 40);
            }
        }

        async function toggleSetting(key) {
            const isChecked = document.getElementById(`toggle-${key.split('_')[0]}`).checked;
            sendSettingUpdate({ [key]: isChecked });
        }

        async function setTradingMode(mode) {
            sendSettingUpdate({ "trading_mode": mode });
        }

        async function saveRiskSetting(val) {
            sendSettingUpdate({ "risk_percent": parseFloat(val) });
        }

        async function sendSettingUpdate(payload) {
            try {
                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    fetchStatus();
                }
            } catch (e) {
                console.error("Failed to update setting", e);
            }
        }

        async function triggerTraining() {
            try {
                const response = await fetch('/api/train', { method: 'POST' });
                if (response.ok) {
                    alert("AI Auto-Training Job has been successfully triggered on background thread!");
                    fetchStatus();
                }
            } catch (e) {
                console.error("Failed to trigger training", e);
            }
        }

        async function panicCloseAll() {
            if (confirm("🚨 EMERGENCY: Are you absolutely sure you want to close ALL active positions?")) {
                try {
                    const response = await fetch('/api/close_all', {
                        method: 'POST'
                    });
                    if (response.ok) {
                        const result = await response.json();
                        alert(`Panic close completed successfully!\nClosed positions: ${result.closed.join(', ')}\nErrors: ${result.errors.join(', ')}`);
                        fetchStatus();
                    } else {
                        alert("Panic close request failed.");
                    }
                } catch (e) {
                    console.error("Failed to execute panic close", e);
                    alert("Network error occurred during panic close execution.");
                }
            }
        }

        // Poll status every 1.5 seconds
        setInterval(fetchStatus, 1500);
        fetchStatus();
    </script>
</body>
</html>
"""

class DashboardRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, engine, *args, **kwargs):
        self.engine = engine
        super().__init__(*args, **kwargs)
        
    def log_message(self, format, *args):
        # Suppress logging in console to avoid cluttering MT5 execution loop
        pass
        
    def _set_headers(self, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
    def do_OPTIONS(self):
        self._set_headers(status=200)
        
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == "/":
            self._set_headers("text/html; charset=utf-8")
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif path == "/api/status":
            self._set_headers()
            status_data = self._get_status_data()
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
        elif path == "/api/journal":
            try:
                from core.trade_journal import trade_journal
                trades = trade_journal.get_all_trades()
                self._set_headers()
                self.wfile.write(json.dumps({"trades": trades[-200:], "total": len(trades)}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/daily_report":
            try:
                report = self.engine.daily_analyzer.get_latest_report()
                from core.trade_journal import trade_journal
                today_summary = trade_journal.get_daily_summary()
                self._set_headers()
                self.wfile.write(json.dumps({
                    "report": report,
                    "today_summary": today_summary
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif path == "/api/backtest_results":
            try:
                results = self.engine.backtester.get_last_results()
                self._set_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")
            
    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        if path == "/api/settings":
            try:
                data = json.loads(post_data.decode('utf-8'))
                for key, val in data.items():
                    settings_manager.set(key, val)
                self._set_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=400)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif path == "/api/train":
            try:
                # Trigger training in a background thread to prevent blocking
                training_thread = threading.Thread(target=self._run_training_job, daemon=True)
                training_thread.start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "training_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/close_all":
            try:
                res = self.engine.close_all_positions()
                self._set_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/journal":
            try:
                from core.trade_journal import trade_journal
                trades = trade_journal.get_all_trades()
                # Return last 200 trades
                self._set_headers()
                self.wfile.write(json.dumps({"trades": trades[-200:], "total": len(trades)}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/daily_report":
            try:
                report = self.engine.daily_analyzer.get_latest_report()
                from core.trade_journal import trade_journal
                yesterday_summary = trade_journal.get_daily_summary()
                self._set_headers()
                self.wfile.write(json.dumps({
                    "report": report,
                    "today_summary": yesterday_summary
                }).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/run_analysis":
            try:
                def _run():
                    from datetime import date
                    self.engine.daily_analyzer.analyze_date(date.today())
                threading.Thread(target=_run, daemon=True).start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "analysis_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/run_backtest":
            try:
                def _run():
                    symbol = self.engine.symbols[0] if self.engine.symbols else "XAUUSDm"
                    trading_mode = settings_manager.get("trading_mode", "scalping")
                    self.engine.backtester.self_optimize(symbol, trading_mode=trading_mode)
                threading.Thread(target=_run, daemon=True).start()
                self._set_headers()
                self.wfile.write(json.dumps({"status": "backtest_started"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif path == "/api/backtest_results":
            try:
                results = self.engine.backtester.get_last_results()
                self._set_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            except Exception as e:
                self._set_headers(status=500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")

    def _run_training_job(self):
        # Prevent double triggers
        if hasattr(self.engine, 'training_in_progress') and self.engine.training_in_progress:
            return
        
        self.engine.training_in_progress = True
        try:
            self.engine.trigger_historical_training()
        except Exception as e:
            self.engine.logger.error(f"Failed to auto-train pattern database: {e}")
        finally:
            self.engine.training_in_progress = False
            
    def _get_status_data(self) -> Dict[str, Any]:
        """Gather all running state, volume and sentiment data for client"""
        try:
            # 1. Determine broker status
            account = mt5.account_info()
            broker_name = account.company if account else "GENERIC"
            server_name = account.server if account else "DEMO"
            login_num = account.login if account else 0
            
            is_paper = settings_manager.get("paper_mode", True)
            if is_paper:
                balance = getattr(self.engine.trade_manager, 'virtual_balance', 10000.0)
                equity = getattr(self.engine.trade_manager, 'virtual_equity', 10000.0)
                profit = equity - balance
            else:
                balance = account.balance if account else 0.0
                equity = account.equity if account else 0.0
                profit = account.profit if account else 0.0
                
            account_data = {
                "broker": broker_name,
                "server": server_name,
                "login": login_num,
                "balance": balance,
                "equity": equity,
                "profit": profit,
                "mode": "paper" if is_paper else "live"
            }
            
            leverage_str = f"1:{account.leverage}" if (account and getattr(account, 'leverage', None)) else "N/A"
            margin_level_str = f"{account.margin_level:.1f}%" if (account and getattr(account, 'margin_level', None) and account.margin_level > 0) else "N/A"
            loop_latency = self.engine.market_state.get('latency_ms', 0.0)
            
            # Fetch current spread and max_spread_points
            spread_data = {}
            if len(self.engine.symbols) > 0:
                symbol = self.engine.symbols[0]
                tick = mt5.symbol_info_tick(symbol)
                symbol_info = mt5.symbol_info(symbol)
                if tick and symbol_info:
                    spread_points = (tick.ask - tick.bid) / symbol_info.point
                    max_spread = settings_manager.get("max_spread_points", 20)
                    spread_data = {
                        "symbol": symbol,
                        "current": round(spread_points, 1),
                        "max_limit": max_spread,
                        "exceeded": spread_points > max_spread
                    }
                else:
                    spread_data = {
                        "symbol": symbol,
                        "current": None,
                        "max_limit": settings_manager.get("max_spread_points", 20),
                        "exceeded": False
                    }
            
            # 2. Settings mapping
            active_settings = settings_manager.get_all()
            
            # 3. Sentiment stats (default values)
            sent_d1 = 0.0
            sent_h4 = 0.0
            sent_h1 = 0.0
            sent_m30 = 0.0
            sent_m15 = 0.0
            sent_m5 = 0.0
            sent_m1 = 0.0
            h1_lbl = "Neutral"
            m15_lbl = "Neutral"
            m5_lbl = "Neutral"
            
            # Fetch from cache calculated in core/engine.py
            sentiment_cache = getattr(self.engine, 'sentiment_cache', {})
            if sentiment_cache:
                sent_d1 = sentiment_cache.get('d1', 0.0)
                sent_h4 = sentiment_cache.get('h4', 0.0)
                sent_h1 = sentiment_cache.get('h1', 0.0)
                sent_m30 = sentiment_cache.get('m30', 0.0)
                sent_m15 = sentiment_cache.get('m15', 0.0)
                sent_m5 = sentiment_cache.get('m5', 0.0)
                sent_m1 = sentiment_cache.get('m1', 0.0)
                
                h1_lbl = "Bullish" if sent_h1 > 0.15 else ("Bearish" if sent_h1 < -0.15 else "Neutral")
                m15_lbl = "Bullish" if sent_m15 > 0.15 else ("Bearish" if sent_m15 < -0.15 else "Neutral")
                m5_lbl = "Bullish" if sent_m5 > 0.15 else ("Bearish" if sent_m5 < -0.15 else "Neutral")
                
            from utils.sentiment_analyzer import sentiment_analyzer
            news_state = sentiment_analyzer.get_news_state()
            
            sentiment_data = {
                "d1": sent_d1,
                "h4": sent_h4,
                "h1": sent_h1,
                "m30": sent_m30,
                "m15": sent_m15,
                "m5": sent_m5,
                "m1": sent_m1,
                "h1_bias_label": h1_lbl,
                "m15_sweep_label": m15_lbl,
                "m5_mss_label": m5_lbl,
                "news": news_state.get("score", 0.0),
                "news_articles": news_state.get("articles", [])
            }
            
            # 4. Volume metrics (default values)
            volume_cache = getattr(self.engine, 'volume_cache', {})
            volume_data = {
                "rvol": volume_cache.get("rvol", 1.0),
                "buy_pressure": volume_cache.get("buy_pressure", 50.0),
                "sell_pressure": volume_cache.get("sell_pressure", 50.0),
                "profile": volume_cache.get("profile", {})
            }
            
            # 5. Position parsing
            active_pos = []
            if hasattr(self.engine.trade_manager, 'positions'):
                for p in self.engine.trade_manager.positions.values():
                    symbol_info = mt5.symbol_info(p.symbol)
                    sl_usd = 0.0
                    tp_usd = 0.0
                    if symbol_info:
                        point_value = symbol_info.trade_tick_value * (symbol_info.point / symbol_info.trade_tick_size)
                        # SL projection
                        if p.sl != 0:
                            if p.action == "BUY":
                                sl_diff_points = (p.entry_price - p.sl) / symbol_info.point
                            else:
                                sl_diff_points = (p.sl - p.entry_price) / symbol_info.point
                            sl_usd = -1 * (sl_diff_points * point_value * p.volume)
                            
                        # TP projection
                        if p.tp != 0:
                            if p.action == "BUY":
                                tp_diff_points = (p.tp - p.entry_price) / symbol_info.point
                            else:
                                tp_diff_points = (p.entry_price - p.tp) / symbol_info.point
                            tp_usd = tp_diff_points * point_value * p.volume
                            
                    active_pos.append({
                        "id": p.id,
                        "symbol": p.symbol,
                        "action": p.action,
                        "volume": p.volume,
                        "entry_price": p.entry_price,
                        "sl": p.sl,
                        "tp": p.tp,
                        "pnl": p.pnl,
                        "sl_usd": round(sl_usd, 2) if sl_usd != 0 else None,
                        "tp_usd": round(tp_usd, 2) if tp_usd != 0 else None,
                        "sibling_id": p.sibling_id
                    })
                    
            closed_pos = []
            if hasattr(self.engine.trade_manager, 'closed_positions'):
                for p in self.engine.trade_manager.closed_positions:
                    closed_pos.append({
                        "id": p.id,
                        "symbol": p.symbol,
                        "action": p.action,
                        "volume": p.volume,
                        "entry_price": p.entry_price,
                        "close_price": p.close_price,
                        "close_time": str(p.close_time),
                        "close_reason": p.close_reason,
                        "pnl": p.pnl
                    })
                    
            regime = "RANGING"
            if hasattr(self.engine, 'pattern_learner') and len(self.engine.symbols) > 0:
                regime = self.engine.pattern_learner.get_market_regime(self.engine.symbols[0])
                
            # Gather prediction data and skipped stats
            prediction_data = {}
            if len(self.engine.symbols) > 0:
                try:
                    prediction_data = self.engine.get_prediction_data(self.engine.symbols[0])
                except Exception:
                    pass

            skipped_stats = getattr(self.engine, 'skipped_stats', {})

            return {
                "account": account_data,
                "settings": active_settings,
                "sentiment": sentiment_data,
                "volume": volume_data,
                "positions": active_pos,
                "history": closed_pos,
                "market_regime": regime,
                "training_status": "training" if getattr(self.engine, 'training_in_progress', False) else "idle",
                "leverage": leverage_str,
                "margin_level": margin_level_str,
                "latency_ms": round(loop_latency, 1),
                "spread": spread_data,
                "prediction": prediction_data,
                "skipped_stats": skipped_stats
            }
        except Exception as e:
            logging.getLogger("PulseViper.WebDashboard").error(f"Error gathering status json: {e}")
            return {
                "account": {"broker": "ERROR", "balance": 0, "equity": 0, "profit": 0},
                "settings": {},
                "sentiment": {"h1": 0, "m15": 0, "m5": 0, "news": 0, "news_articles": []},
                "volume": {"rvol": 1, "buy_pressure": 50, "sell_pressure": 50, "profile": {}},
                "positions": [],
                "history": [],
                "market_regime": "RANGING",
                "training_status": "idle",
                "leverage": "N/A",
                "margin_level": "N/A",
                "latency_ms": 0.0,
                "spread": {}
            }


class WebDashboardServer:
    def __init__(self, engine, port=8000):
        self.engine = engine
        self.port = port
        self.server = None
        self.thread = None
        self.logger = logging.getLogger("PulseViper.WebDashboard")
        
    def start(self):
        handler_factory = lambda *args, **kwargs: DashboardRequestHandler(self.engine, *args, **kwargs)
        self.server = HTTPServer(('127.0.0.1', self.port), handler_factory)
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        self.logger.info(f"Glassmorphic Web Control Dashboard running at http://localhost:{self.port}")
        
    def _run_server(self):
        try:
            self.server.serve_forever()
        except Exception as e:
            self.logger.error(f"Web Dashboard Server error: {e}")
            
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)
