import gspread
import sys
import os
import pickle
from collections import defaultdict
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google.oauth2.service_account import Credentials


def load_backtest_rows():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Trading Bot Log")
    bt = sheet.worksheet("Backtest Results")
    return bt.get_all_values()


def dedupe_signals(rows):
    """Same 18-day non-overlap rule as the simulator, for consistency."""
    by_ticker = defaultdict(list)

    for row in rows[1:]:
        try:
            if len(row) < 23 or not row[16]:
                continue
            date = datetime.strptime(row[0], '%Y-%m-%d')
            by_ticker[row[1]].append({
                "date": date,
                "ticker": row[1],
                "sector": row[2],
                "price": float(row[3]) if row[3] else 0,
                "score": float(row[4]) if row[4] else 0,
                "trend_score": float(row[5]) if row[5] else 0,
                "sector_score": float(row[6]) if row[6] else 0,
                "mr_score": float(row[7]) if row[7] else 0,
                "vol_score": float(row[8]) if row[8] else 0,
                "outcome": row[16],
                "mode": row[18] if len(row) > 18 else "NEUTRAL",
                "vix": float(row[21]) if len(row) > 21 and row[21] else 20.0,
                "regime": row[22] if len(row) > 22 else "UNKNOWN",
            })
        except Exception:
            continue

    deduped = []
    for ticker, trades in by_ticker.items():
        trades.sort(key=lambda x: x["date"])
        last_date = None
        for t in trades:
            if last_date is None or (t["date"] - last_date).days >= 18:
                deduped.append(t)
                last_date = t["date"]

    return deduped


def build_dataframe(deduped):
    df = pd.DataFrame(deduped)
    df = df[df["outcome"].isin(["WIN", "LOSS"])].copy()
    df["label"] = (df["outcome"] == "WIN").astype(int)

    # One-hot encode categorical features
    df = pd.get_dummies(df, columns=["sector", "mode", "regime"], prefix=["sector", "mode", "regime"])

    return df


def train_model(df):
    feature_cols = [c for c in df.columns if c not in ["date", "ticker", "price", "outcome", "label"]]

    X = df[feature_cols]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    print(f"Training rows: {len(X_train)}  |  Test rows: {len(X_test)}")
    print(f"Win rate in training data: {round(y_train.mean()*100, 1)}%")
    print(f"Win rate in test data:     {round(y_test.mean()*100, 1)}%")

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]

    acc = round(accuracy_score(y_test, preds) * 100, 2)
    auc = round(roc_auc_score(y_test, probs), 3)

    print(f"\nTest Accuracy: {acc}%")
    print(f"Test AUC:      {auc}  (0.5 = random guessing, 1.0 = perfect)")
    print("\nClassification report:")
    print(classification_report(y_test, preds, target_names=["LOSS", "WIN"]))

    importances = pd.Series(model.feature_importances_, index=feature_cols)
    importances = importances.sort_values(ascending=False)

    print("\nTOP 15 MOST IMPORTANT FEATURES (what the model actually learned matters):")
    print("=" * 55)
    for feat, imp in importances.head(15).items():
        bar = "█" * int(imp * 200)
        print(f"  {feat:<30} {imp:.4f}  {bar}")

    return model, feature_cols, importances


def save_model(model, feature_cols):
    with open("ml/trained_model.pkl", "wb") as f:
        pickle.dump({"model": model, "feature_cols": feature_cols}, f)
    print("\nModel saved to ml/trained_model.pkl")


if __name__ == "__main__":
    print("Loading backtest data...")
    rows = load_backtest_rows()
    print(f"Raw rows: {len(rows)-1}")

    print("Deduplicating overlapping signals...")
    deduped = dedupe_signals(rows)
    print(f"Deduplicated rows: {len(deduped)}")

    print("\nBuilding training dataframe...")
    df = build_dataframe(deduped)
    print(f"Rows with valid WIN/LOSS outcome: {len(df)}")

    if len(df) < 100:
        print("\nNot enough labeled data yet to train reliably. Need at least ~100+ deduplicated outcomes.")
    else:
        print("\nTraining Random Forest model...\n")
        model, feature_cols, importances = train_model(df)
        save_model(model, feature_cols)
        
        