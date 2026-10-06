import json
import logging
from pathlib import Path

import joblib
import numpy as np
import shap
import xgboost as xgb

logger = logging.getLogger("kronos")

MODEL_DIR = Path(__file__).resolve().parent


def _resolve_model_path(path_str: str) -> str:
    """Resolve model artifact paths from MODEL_DIR, relative models/ or CWD."""
    filename = Path(path_str).name
    p1 = MODEL_DIR / filename
    if p1.exists():
        return str(p1)
    p2 = MODEL_DIR / path_str
    if p2.exists():
        return str(p2)
    p3 = Path(path_str)
    if p3.exists():
        return str(p3)
    return str(p1)


# Hook to handle unpickling cross-platform/GPU serialized Booster in stage1_calibrated
_orig_booster_setstate = xgb.core.Booster.__setstate__


def _patch_booster_setstate(self, state):
    try:
        _orig_booster_setstate(self, state)
    except Exception as exc:
        if "input stream corrupted" in str(exc):
            json_path = _resolve_model_path("stage1_binary_20260927_184325.json")
            b = xgb.Booster()
            b.load_model(str(json_path))
            self.__dict__.update(state)
            self.handle = b.handle
            b.handle = None  # Transfer ownership to prevent double-free on shutdown
        else:
            raise


# --- Load artifacts once at startup ---
SCALER = joblib.load(_resolve_model_path("models/scaler.joblib"))
LABEL_ENCODER = joblib.load(_resolve_model_path("models/label_encoder.joblib"))
with open(_resolve_model_path("models/label_mapping.json")) as f:
    LABEL_MAPPING = {int(k): v for k, v in json.load(f).items()}
with open(_resolve_model_path("models/feature_columns.json")) as f:
    FEATURE_COLUMNS = json.load(f)

with open(_resolve_model_path("models/stage2_label_mapping.json")) as f:
    STAGE2_LABEL_MAPPING = {int(k): v for k, v in json.load(f).items()}

xgb.core.Booster.__setstate__ = _patch_booster_setstate
try:
    STAGE1_MODEL = joblib.load(
        _resolve_model_path("models/stage1_calibrated_20260927_184325.joblib")
    )
finally:
    xgb.core.Booster.__setstate__ = _orig_booster_setstate

STAGE2_MODEL = xgb.XGBClassifier()
STAGE2_MODEL.load_model(
    _resolve_model_path("models/stage2_multiclass_20260927_184325.json")
)
EXPLAINER = shap.TreeExplainer(STAGE2_MODEL)


def predict(sample: dict) -> dict:
    """
    Real-model replacement for mock_detector.predict(). Same input/output contract.
    sample: dict of {feature_name: value} matching FEATURE_COLUMNS
    """
    row = np.array(
        [[sample.get(col, 0.0) for col in FEATURE_COLUMNS]], dtype=np.float32
    )
    row_scaled = SCALER.transform(row)

    bin_pred = STAGE1_MODEL.predict(row_scaled)[0]
    bin_conf = STAGE1_MODEL.predict_proba(row_scaled)[0][bin_pred]

    if bin_pred == 0:
        prediction = "Benign"
        confidence = float(bin_conf)
        top_features = []
    else:
        multi_pred = STAGE2_MODEL.predict(row_scaled)[0]
        multi_proba = STAGE2_MODEL.predict_proba(row_scaled)[0]
        prediction = STAGE2_LABEL_MAPPING[int(multi_pred)]
        confidence = float(multi_proba[multi_pred])

        # shap here returns one ndarray of shape (n_samples, n_features,
        # n_classes) for multiclass, not a list-per-class -- slice out the
        # predicted class correctly in either format.
        raw_shap = EXPLAINER.shap_values(row_scaled)
        if isinstance(raw_shap, list):
            shap_row = raw_shap[multi_pred][0]
        else:
            shap_row = raw_shap[0, :, multi_pred]

        top_idx = np.argsort(np.abs(shap_row))[::-1][:5]
        top_features = [
            {
                "feature": FEATURE_COLUMNS[i],
                "value": float(row[0][i]),
                "shap_value": round(float(shap_row[i]), 4),
                "direction": "increases risk" if shap_row[i] > 0 else "decreases risk",
            }
            for i in top_idx
        ]

    return {
        "prediction": prediction,
        "confidence": round(confidence, 4),
        "top_features": top_features,
    }
