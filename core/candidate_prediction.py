# core/candidate_prediction.py
from dataclasses import dataclass

@dataclass(frozen=True)
class CandidatePrediction:
    candidate_id: str

    probability_tp_first: float
    probability_sl_first: float
    probability_timeout: float

    calibrated_probability_tp_first: float
    probability_lower_bound: float

    expected_net_r: float
    expected_mfe_r: float
    expected_mae_r: float
    expected_holding_bars: float

    net_r_q10: float
    net_r_q50: float
    net_r_q90: float

    execution_cost_r: float

    epistemic_uncertainty: float
    aleatoric_uncertainty: float
    out_of_distribution_score: float

    model_version: str
    calibration_version: str
    feature_schema_hash: str
