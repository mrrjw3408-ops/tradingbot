import pickle
import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_model():
    with open("ml/trained_model.pkl", "rb") as f:
        data = pickle.load(f)
    return data["model"], data["feature_cols"]


def build_feature_row(score, trend_score, sector_score, mr_score, vol_score,
                       vix, sector, mode, regime, feature_cols):
    """
    Builds a single-row dataframe matching exactly the one-hot encoded
    feature columns the model was trained on, filling in 0 for any
    sector/mode/regime category not present in this particular row.
    """
    row = {
        "score": score,
        "trend_score": trend_score,
        "sector_score": sector_score,
        "mr_score": mr_score,
        "vol_score": vol_score,
        "vix": vix,
    }

    # Initialize every known one-hot column to 0
    for col in feature_cols:
        if col not in row:
            row[col] = 0

    # Flip on the matching categorical columns if they exist in the model
    sector_col = f"sector_{sector}"
    mode_col = f"mode_{mode}"
    regime_col = f"regime_{regime}"

    if sector_col in row:
        row[sector_col] = 1
    if mode_col in row:
        row[mode_col] = 1
    if regime_col in row:
        row[regime_col] = 1

    df = pd.DataFrame([row])
    df = df[feature_cols]  # enforce exact column order the model expects
    return df


def predict_win_probability(score, trend_score, sector_score, mr_score, vol_score,
                             vix, sector, mode, regime):
    model, feature_cols = load_model()
    X = build_feature_row(score, trend_score, sector_score, mr_score, vol_score,
                           vix, sector, mode, regime, feature_cols)
    prob = model.predict_proba(X)[0][1]
    return round(float(prob) * 100, 1)


def predict_batch(stocks):
    """
    stocks: list of dicts, each with keys:
      score, trend_score, sector_score, mr_score, vol_score, vix, sector, mode, regime
    Returns the same list with a 'ml_probability' key added, sorted descending.
    """
    model, feature_cols = load_model()
    results = []

    for s in stocks:
        X = build_feature_row(
            s["score"], s["trend_score"], s["sector_score"], s["mr_score"],
            s["vol_score"], s["vix"], s["sector"], s["mode"], s["regime"],
            feature_cols
        )
        prob = model.predict_proba(X)[0][1]
        s = dict(s)
        s["ml_probability"] = round(float(prob) * 100, 1)
        results.append(s)

    results.sort(key=lambda x: x["ml_probability"], reverse=True)
    return results


if __name__ == "__main__":
    print("Testing ML prediction on a few hypothetical setups...\n")

    test_cases = [
        {"label": "Strong momentum, bull, low VIX",
         "score": 4.5, "trend_score": 2.0, "sector_score": 1.5, "mr_score": 0.5,
         "vol_score": 0.5, "vix": 13.0, "sector": "Semiconductors", "mode": "MOMENTUM", "regime": "BULL"},

        {"label": "Mean reversion, bear, high VIX",
         "score": 3.0, "trend_score": 0.5, "sector_score": 0.0, "mr_score": 1.5,
         "vol_score": 0.5, "vix": 32.0, "sector": "Finance", "mode": "MEAN_REVERSION", "regime": "BEAR"},

        {"label": "Neutral everything, moderate VIX",
         "score": 2.0, "trend_score": 1.0, "sector_score": 0.5, "mr_score": 0.0,
         "vol_score": 0.0, "vix": 19.0, "sector": "Industrials", "mode": "NEUTRAL", "regime": "NEUTRAL"},
    ]

    for case in test_cases:
        label = case.pop("label")
        prob = predict_win_probability(**case)
        print(f"{label}: {prob}% win probability")
        