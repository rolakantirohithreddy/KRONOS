# KRONOS XGBoost Detection Model — Training Report
Generated: 2026-09-27T19:03:32.111678

## Dataset
- Source files: 63 merged CSV shards
- Total rows after cleaning: 3,839,370
- Features used: 39
- Label column: `Label`

## Split
- Train: 2,687,559 | Val: 575,905 | Test: 575,906
- Split indices saved to `models/split_indices.npz` for reuse across any comparison model.

## Class Imbalance Handling
- Majority classes undersampled in training set only (cap = 577,780 rows, see `reports/class_distribution_after_balancing.csv`)
- Remaining minority classes boosted with targeted SMOTE
- Class-weighted sample weights applied on top of resampling
- Validation/test sets left untouched (real-world class frequencies preserved for honest evaluation)

## Model Architecture
- Two-stage XGBoost, GPU-trained (`device="cuda"`)
- Stage 1: Binary (Benign vs Attack)
- Stage 2: Multiclass attack-type (33 classes), trained only on attack rows

## Hyperparameter Tuning
- Optuna, 30 trials per stage, 3-fold stratified CV
- Stage 1 best macro-F1 (CV): 0.9049
- Stage 2 best macro-F1 (CV): 0.8370
- Full params saved to `models/best_hyperparams.json`

## Final Test Set Performance
- Stage 1 ROC-AUC: 0.9970
- Stage 2 Macro F1: 0.6277 | Weighted F1: 0.7782
- 5-fold CV stability (Stage 1): mean 0.9910, std 0.0001

## Robustness
- Gaussian noise degradation: see `reports/robustness_gaussian_noise.csv` and `plots/robustness_gaussian.png`
- FGSM-adapted (surrogate-gradient) degradation: see `reports/robustness_fgsm_adapted.csv`
- Note: exact FGSM requires a differentiable model; XGBoost's trees are not differentiable, so a
  logistic-regression surrogate was used to compute the gradient direction, applied to real test data.

## Inference Latency
{
  "single_sample_mean_ms": 430.84180294496036,
  "single_sample_p95_ms": 464.04575424712675,
  "single_sample_p99_ms": 476.53080599498924,
  "batch_1000_total_ms": 5.6572799949208274,
  "batch_1000_per_sample_ms": 0.0056572799949208274
}

## Calibration
- Applied via `CalibratedClassifierCV` (sigmoid, prefit on validation set)
- Reliability diagram: `plots/calibration_reliability.png`

## Explainability
- SHAP TreeExplainer on Stage 2, sampled on 2000 test rows
- Global summary: `plots/shap_summary_stage2.png`
- Per-prediction explanation function: `explain_prediction()` in this notebook, packaged as `models/inference.py`

## Artifacts produced
- `models/stage1_binary_20260927_184325.json`, `models/stage1_calibrated_20260927_184325.joblib`
- `models/stage2_multiclass_20260927_184325.json`
- `models/scaler.joblib`, `models/label_encoder.joblib`, `models/label_mapping.json`, `models/feature_columns.json`
- `models/split_indices.npz`, `models/best_hyperparams.json`
- `models/inference.py` — drop-in replacement for `mock_detector.py` in the FastAPI backend
