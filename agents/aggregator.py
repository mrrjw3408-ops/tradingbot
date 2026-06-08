import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ENTRY_THRESHOLD_BULL, ENTRY_THRESHOLD_NEUTRAL, ENTRY_THRESHOLD_BEAR

def get_entry_threshold(regime):
    if regime == "BULL":
        return ENTRY_THRESHOLD_BULL
    elif regime == "NEUTRAL":
        return ENTRY_THRESHOLD_NEUTRAL
    else:
        return ENTRY_THRESHOLD_BEAR

def aggregate_signals(scan_results, regime_data):
    regime = regime_data["regime"]
    threshold = get_entry_threshold(regime)
    
    strong_signals = []
    watchlist = []
    
    print("=" * 50)
    print(f"AGGREGATING SIGNALS — {regime} REGIME")
    print(f"Entry threshold: {threshold}/10")
    print("=" * 50)
    
    for stock in scan_results:
        ticker = stock["ticker"]
        sector = stock["sector"]
        score = stock["score"]
        
        # Regime adjustment
        adjusted_score = score
        
        if adjusted_score >= threshold:
            strong_signals.append({
                "ticker": ticker,
                "sector": sector,
                "score": adjusted_score,
                "regime": regime,
                "threshold": threshold
            })
        elif adjusted_score >= threshold - 1.5:
            watchlist.append({
                "ticker": ticker,
                "sector": sector, 
                "score": adjusted_score
            })
    
    # Sort by score
    strong_signals.sort(key=lambda x: x["score"], reverse=True)
    watchlist.sort(key=lambda x: x["score"], reverse=True)
    
    print(f"\nSTRONG SIGNALS ({len(strong_signals)}):")
    for s in strong_signals:
        print(f"  {s['ticker']} ({s['sector']}): {s['score']}/10")
    
    print(f"\nWATCH LIST ({len(watchlist)}):")
    for s in watchlist[:10]:
        print(f"  {s['ticker']} ({s['sector']}): {s['score']}/10")
    
    return strong_signals, watchlist

if __name__ == "__main__":
    # Test with sample data
    test_results = [
        {"ticker": "CRWD", "sector": "Backdoor Tech", "score": 8.5},
        {"ticker": "ARM", "sector": "Semiconductors", "score": 7.5},
        {"ticker": "MS", "sector": "Finance", "score": 6.5},
        {"ticker": "AAPL", "sector": "Backdoor Tech", "score": 4.0},
    ]
    test_regime = {"regime": "NEUTRAL", "score": 1, "threshold_adjustment": 1}
    aggregate_signals(test_results, test_regime)
