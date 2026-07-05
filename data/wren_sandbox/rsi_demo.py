def compute_rsi(closes, period=14):
    delta = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in delta]
    losses = [-d if d < 0 else 0 for d in delta]
    avg_gain = sum(gains[:period]) / period
    avg_loss = abs(sum(losses[:period]) / period)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

if __name__ == '__main__':
    print(compute_rsi([44,44.34,44.09,44.15,44.28,44.44,43.61,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61]))