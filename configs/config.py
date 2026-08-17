class Config:
    """
    Static infrastructure defaults only.

    Runtime trading/risk settings are owned by:

        utils.settings_manager.settings_manager

    These compatibility constants deliberately match the safe defaults so
    legacy readers cannot silently apply a contradictory policy.
    """

    # ------------------------------------------------------------------
    # MT5 / infrastructure
    # ------------------------------------------------------------------

    MT5_PATH = None

    MAGIC_NUMBER = 123456

    # ------------------------------------------------------------------
    # Paper simulation
    # ------------------------------------------------------------------

    INITIAL_BALANCE = 10000.0

    # ------------------------------------------------------------------
    # LEGACY COMPATIBILITY MIRRORS
    #
    # Runtime execution code should NOT use these when a dynamic setting
    # exists. Use settings_manager.get(...) instead.
    # ------------------------------------------------------------------

    PAPER_MODE = True

    # Percent units:
    #
    # 0.05 = 0.05%
    RISK_PERCENT = 0.05

    MAX_SPREAD_POINTS = 120

    MIN_RR_RATIO = 1.5

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    LONDON_SESSION = (
        8,
        16,
    )

    NY_SESSION = (
        13,
        21,
    )

    ASIAN_SESSION = (
        0,
        8,
    )

    # ------------------------------------------------------------------
    # Data / logs
    # ------------------------------------------------------------------

    HISTORY_BARS = 2000

    LOG_PATH = (
        "logs/signals.csv"
    )