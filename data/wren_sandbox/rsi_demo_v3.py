import numpy as np

def compute_rsi(prices):
    delta = np.diff(prices)
    gains = delta * 0
    losses = gains.copy()
    gains[delta > 0] = delta[delta > 0]
    losses[delta < 0] = -delta[delta < 0]
    avg_gains = np.zeros(len(gains))
    avg_losses = np.zeros(len(losses))
    avg_gains[:14] = gains[:14]
    avg_losses[:14] = losses[:14]
    for i in range(14, len(avg_gains)):
        avg_gains[i] = (avg_gains[i-1]*13 + gains[i]) / 14
        avg_losses[i] = (avg_losses[i-1]*13 + losses[i]) / 14
    rs = avg_gains[-1] / avg_losses[-1]
    rsi = 100 - (100 / (1 + rs))
    return rsi

if __name__ == '__main__':
    prices = [44,44.34,44.09,44.15,44.28,44.44,43.61,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61]
    print(compute_rsi(prices))