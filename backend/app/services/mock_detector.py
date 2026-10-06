"""Mock intrusion detector used until the trained model is available."""

import random
import time
from typing import Any

ATTACK_TYPES = (
    "DDoS",
    "DoS",
    "Recon",
    "Mirai",
    "Spoofing",
    "BruteForce",
    "Benign",
)
FALLBACK_FEATURES = ("flow_duration", "packet_rate", "byte_count", "dst_port")


def predict(sample: dict[str, float]) -> dict[str, Any]:
    """Return a realistic mock classification and feature explanation."""
    started_at = time.perf_counter()
    time.sleep(random.uniform(0.006, 0.018))

    prediction = random.choice(ATTACK_TYPES)
    available_features = list(sample) or list(FALLBACK_FEATURES)
    selected_features = random.sample(
        available_features,
        k=min(2, len(available_features)),
    )
    top_features = []

    for index, feature_name in enumerate(selected_features):
        increases_risk = prediction != "Benign" and index == 0
        shap_magnitude = random.uniform(0.08, 0.42)
        top_features.append(
            {
                "feature": feature_name,
                "value": sample.get(feature_name, round(random.uniform(1, 150), 2)),
                "shap_value": round(shap_magnitude if increases_risk else -shap_magnitude, 3),
                "direction": "increases risk" if increases_risk else "decreases risk",
            }
        )

    latency_ms = (time.perf_counter() - started_at) * 1000
    return {
        "prediction": prediction,
        "confidence": round(random.uniform(0.78, 0.99), 2),
        "top_features": top_features,
        "latency_ms": round(latency_ms, 2),
    }